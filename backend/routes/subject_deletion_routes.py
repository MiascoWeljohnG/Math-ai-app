from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_admin, require_teacher_or_admin
from database import get_db
from models import Lesson, Subject, SubjectDeletionRequest, SubjectDeletionVote, User
from routes.subjects_routes import delete_subject_cascade
from school import shared_subjects
from notifications import notify_admins

router = APIRouter(prefix="/subject-deletions", tags=["subject-deletions"])


def _admin_usernames(db: Session) -> set[str]:
    return {username for (username,) in db.query(User.username).filter(User.role == "admin")}

def _school_admin_usernames(db: Session, school_id: int) -> set[str]:
    if not school_id:
        return set()
    return {username for (username,) in db.query(User.username).filter(User.role == "school_admin", User.school_id == school_id)}

def _votes(db: Session, request_id: int) -> dict[str, bool]:
    rows = db.query(SubjectDeletionVote).filter(SubjectDeletionVote.request_id == request_id)
    return {vote.admin_username: vote.approve for vote in rows}


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() + "Z" if moment else None


def _serialize(db: Session, request: SubjectDeletionRequest, viewer: User) -> dict:
    subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
    school_id = subject.school_id if subject else None
    
    admins = _admin_usernames(db)
    school_admins = _school_admin_usernames(db, school_id)
    
    votes = _votes(db, request.id)
    my_vote = votes.get(viewer.username)
    
    return {
        "id": request.id,
        "subject_id": request.subject_id,
        "subject_name": request.subject_name,
        "requested_by": request.requested_by,
        "reason": request.reason,
        "status": request.status,
        "created_at": _iso(request.created_at),
        "lesson_count": db.query(func.count(Lesson.id)).filter(Lesson.subject_id == request.subject_id).scalar(),
        "admins_total": len(admins) + len(school_admins),
        "approved_by": sorted(name for name in (admins | school_admins) if votes.get(name) is True),
        "waiting_on": sorted(name for name in (admins | school_admins) if name not in votes),
        "my_vote": None if my_vote is None else ("approve" if my_vote else "reject"),
    }


def _resolve(db: Session, request: SubjectDeletionRequest) -> str:
    """Settle a pending request after a vote. Returns its new status. The caller has not committed yet."""
    votes = _votes(db, request.id)
    if False in votes.values():
        request.status = "rejected"
        # Notify default admins that deletion was declined
        subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
        notify_admins(db, "deletion_declined", "Subject Deletion Declined", f'The deletion request for subject "{request.subject_name}" was rejected.')
    else:
        subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
        school_id = subject.school_id if subject else None
        
        admins = _admin_usernames(db)
        school_admins = _school_admin_usernames(db, school_id)
        
        # Check if we have at least one school admin approval (if there are any school admins for this school)
        has_school_admin_approval = any(votes.get(sa) for sa in school_admins) if school_admins else True
        
        # Check if we have at least one main admin approval
        has_main_admin_approval = any(votes.get(ma) for ma in admins)
        
        if has_school_admin_approval and not has_main_admin_approval:
            # Forwarded to main admin implicitly by just waiting for them
            request.status = "pending_main_admin"
        elif has_school_admin_approval and has_main_admin_approval:
            if subject is not None and subject.owner_user_id is None:
                delete_subject_cascade(db, subject)
            request.status = "approved"
        else:
            return request.status
            
    request.resolved_at = datetime.utcnow()
    return request.status


class DeletionRequest(BaseModel):
    subject_id: int
    reason: Optional[str] = Field(default=None, max_length=300)


@router.post("")
def request_subject_deletion(
    req: DeletionRequest,
    user: User = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
):
    subject = db.query(Subject).filter(Subject.id == req.subject_id, shared_subjects(user)).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    if db.query(SubjectDeletionRequest).filter(
        SubjectDeletionRequest.subject_id == subject.id,
        SubjectDeletionRequest.status.in_(["pending", "pending_main_admin"]),
    ).first():
        raise HTTPException(status_code=409, detail="A deletion request for this subject is already waiting for the admins")

    request = SubjectDeletionRequest(
        subject_id=subject.id,
        subject_name=subject.name,
        requested_by=user.username,
        reason=(req.reason or "").strip() or None,
    )
    db.add(request)
    db.flush()
    if user.role in ["admin", "school_admin"]:
        db.add(SubjectDeletionVote(request_id=request.id, admin_username=user.username, approve=True))
        db.flush()
    status = _resolve(db, request)
    db.commit()
    
    if status == "approved":
        message = f'"{subject.name}" was deleted.'
    elif status == "rejected":
        message = f'Request rejected immediately.'
    else:
        message = f'Request sent. "{subject.name}" will be deleted once approved by the required admins.'
        
    return {"status": status, "message": message, "request_id": request.id}


@router.get("")
def list_pending_requests(user: User = Depends(require_teacher_or_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(SubjectDeletionRequest)
        .filter(SubjectDeletionRequest.status.in_(["pending", "pending_main_admin"]))
        .order_by(SubjectDeletionRequest.created_at.asc(), SubjectDeletionRequest.id.asc())
        .all()
    )
    if user.role != "admin":   # teachers/school_admins see their own school's requests
        mine = {i for (i,) in db.query(Subject.id).filter(shared_subjects(user))}
        rows = [row for row in rows if row.subject_id in mine]
    return [_serialize(db, row, user) for row in rows]


class Decision(BaseModel):
    approve: bool


@router.post("/{request_id}/decision")
def decide(
    request_id: int,
    req: Decision,
    user: User = Depends(require_teacher_or_admin), # Allow school_admin or admin
    db: Session = Depends(get_db),
):
    if user.role not in ["admin", "school_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    request = db.query(SubjectDeletionRequest).filter(SubjectDeletionRequest.id == request_id).first()
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status not in ["pending", "pending_main_admin"]:
        raise HTTPException(status_code=409, detail=f"This request was already {request.status}")

    vote = db.query(SubjectDeletionVote).filter(
        SubjectDeletionVote.request_id == request.id,
        SubjectDeletionVote.admin_username == user.username,
    ).first()
    if vote is None:
        db.add(SubjectDeletionVote(request_id=request.id, admin_username=user.username, approve=req.approve))
    else:
        vote.approve, vote.decided_at = req.approve, datetime.utcnow()
    db.flush()
    status = _resolve(db, request)
    db.commit()
    
    if status in ["pending", "pending_main_admin"]:
        message = "Approved. Waiting for other admins."
    elif status == "approved":
        message = f'Approved. "{request.subject_name}" was deleted.'
    else:
        message = f'Rejected. "{request.subject_name}" stays.'
        
    return {"status": status, "message": message}
