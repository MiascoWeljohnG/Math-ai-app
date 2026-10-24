"""Deleting a shared subject. A teacher (or the school admin) asks; the admin of the subject's school decides.
One approval deletes the subject with its lessons, quizzes and progress; a rejection keeps it. Everything is
limited to the requester's own school, and each request and decision goes into the audit log."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_school_admin, require_staff
from database import get_db
from models import AuditLog, Lesson, Subject, SubjectDeletionRequest, SubjectDeletionVote, User
from routes.subjects_routes import delete_subject_cascade
from school import shared_subjects
from notifications import notify_admins

router = APIRouter(prefix="/subject-deletions", tags=["subject-deletions"])

OPEN = ["pending", "pending_main_admin"]   # the second only appears on requests made under the old two-step rule


def _school_admin_usernames(db: Session, school_id: Optional[int]) -> set[str]:
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
    admins = _school_admin_usernames(db, subject.school_id if subject else None)
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
        "admins_total": len(admins),
        "approved_by": sorted(name for name in admins if votes.get(name) is True),
        "waiting_on": sorted(name for name in admins if name not in votes),
        "my_vote": None if my_vote is None else ("approve" if my_vote else "reject"),
    }


def _resolve(db: Session, request: SubjectDeletionRequest) -> str:
    """Settle a pending request after a vote. Returns its new status. The caller has not committed yet."""
    votes = _votes(db, request.id)
    subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
    admins = _school_admin_usernames(db, subject.school_id if subject else None)
    if False in votes.values():
        request.status = "rejected"
        notify_admins(db, "deletion_declined", "Subject Deletion Declined",
                      f'The deletion request for subject "{request.subject_name}" was rejected.',
                      school_id=subject.school_id if subject else None)
    elif any(votes.get(name) for name in admins):
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
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    subject = db.query(Subject).filter(Subject.id == req.subject_id, shared_subjects(user)).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    if db.query(SubjectDeletionRequest).filter(
        SubjectDeletionRequest.subject_id == subject.id,
        SubjectDeletionRequest.status.in_(OPEN),
    ).first():
        raise HTTPException(status_code=409, detail="A deletion request for this subject is already waiting for the admin")

    request = SubjectDeletionRequest(
        subject_id=subject.id,
        subject_name=subject.name,
        requested_by=user.username,
        reason=(req.reason or "").strip() or None,
    )
    db.add(request)
    db.flush()
    db.add(AuditLog(actor=user.username, school_id=subject.school_id, action="subject.delete.request", target=subject.name, detail=request.reason))
    if user.role == "school_admin":   # asking as the school admin is the same as approving
        db.add(SubjectDeletionVote(request_id=request.id, admin_username=user.username, approve=True))
        db.flush()
    else:
        notify_admins(db, "deletion_request", "Subject deletion requested",
                      f'@{user.username} asked to delete "{subject.name}".', school_id=subject.school_id)
    name = subject.name
    status = _resolve(db, request)
    db.commit()

    if status == "approved":
        message = f'"{name}" was deleted.'
    else:
        message = f'Request sent. "{name}" will be deleted once your school admin approves.'
    return {"status": status, "message": message, "request_id": request.id}


@router.get("")
def list_pending_requests(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    rows = (
        db.query(SubjectDeletionRequest)
        .filter(SubjectDeletionRequest.status.in_(OPEN))
        .order_by(SubjectDeletionRequest.created_at.asc(), SubjectDeletionRequest.id.asc())
        .all()
    )
    mine = {i for (i,) in db.query(Subject.id).filter(shared_subjects(user))}   # own school's subjects only
    return [_serialize(db, row, user) for row in rows if row.subject_id in mine]


class Decision(BaseModel):
    approve: bool


@router.post("/{request_id}/decision")
def decide(
    request_id: int,
    req: Decision,
    user: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    request = db.query(SubjectDeletionRequest).filter(SubjectDeletionRequest.id == request_id).first()
    subject = db.query(Subject).filter(Subject.id == request.subject_id).first() if request else None
    if request is None or subject is None or subject.school_id != user.school_id:   # another school's request looks like it does not exist
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status not in OPEN:
        raise HTTPException(status_code=409, detail=f"This request was already {request.status}")

    vote = db.query(SubjectDeletionVote).filter(
        SubjectDeletionVote.request_id == request.id,
        SubjectDeletionVote.admin_username == user.username,
    ).first()
    if vote is None:
        db.add(SubjectDeletionVote(request_id=request.id, admin_username=user.username, approve=req.approve))
    else:
        vote.approve, vote.decided_at = req.approve, datetime.utcnow()
    db.add(AuditLog(actor=user.username, school_id=subject.school_id, action="subject.delete.approve" if req.approve else "subject.delete.reject", target=request.subject_name))
    db.flush()
    status = _resolve(db, request)
    db.commit()

    if status == "approved":
        message = f'Approved. "{request.subject_name}" was deleted.'
    elif status == "rejected":
        message = f'Rejected. "{request.subject_name}" stays.'
    else:
        message = "Saved."
    return {"status": status, "message": message}
