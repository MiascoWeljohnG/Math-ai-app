"""Deleting a shared subject needs every admin's approval.

  teacher/admin  POST /subject-deletions            ask to delete a subject (admins are notified: the request
                                                    shows up on their dashboard)
  admin          POST /subject-deletions/{id}/decision   approve or reject
  teacher/admin  GET  /subject-deletions            requests still waiting

The subject is removed only when EVERY admin account has approved. One rejection ends the request and
the subject stays. An admin who makes the request counts as having approved it. "Every admin" is
checked when a vote comes in, so an admin added after the request was made also has to approve.
"""
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

router = APIRouter(prefix="/subject-deletions", tags=["subject-deletions"])


def _admin_usernames(db: Session) -> set[str]:
    return {username for (username,) in db.query(User.username).filter(User.role == "admin")}


def _votes(db: Session, request_id: int) -> dict[str, bool]:
    rows = db.query(SubjectDeletionVote).filter(SubjectDeletionVote.request_id == request_id)
    return {vote.admin_username: vote.approve for vote in rows}


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() + "Z" if moment else None   # stored as UTC; the Z lets the browser localise it


def _serialize(db: Session, request: SubjectDeletionRequest, viewer: User) -> dict:
    admins = _admin_usernames(db)
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
    if False in votes.values():
        request.status = "rejected"
    elif _admin_usernames(db) <= {name for name, approve in votes.items() if approve}:
        subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
        if subject is not None and subject.owner_user_id is None:
            delete_subject_cascade(db, subject)
        request.status = "approved"
    else:
        return "pending"
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
        SubjectDeletionRequest.status == "pending",
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
    if user.role == "admin":
        db.add(SubjectDeletionVote(request_id=request.id, admin_username=user.username, approve=True))
        db.flush()
    status = _resolve(db, request)
    db.commit()
    message = {
        "pending": f'Request sent. "{subject.name}" will be deleted once every admin approves.',
        "approved": f'"{subject.name}" was deleted (you are the only admin).',
    }[status]
    return {"status": status, "message": message, "request_id": request.id}


@router.get("")
def list_pending_requests(user: User = Depends(require_teacher_or_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(SubjectDeletionRequest)
        .filter(SubjectDeletionRequest.status == "pending")
        .order_by(SubjectDeletionRequest.created_at.asc(), SubjectDeletionRequest.id.asc())
        .all()
    )
    if user.role != "admin":   # teachers see their own school's requests; the main admin approves everyone's
        mine = {i for (i,) in db.query(Subject.id).filter(shared_subjects(user))}
        rows = [row for row in rows if row.subject_id in mine]
    return [_serialize(db, row, user) for row in rows]


class Decision(BaseModel):
    approve: bool


@router.post("/{request_id}/decision")
def decide(
    request_id: int,
    req: Decision,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    request = db.query(SubjectDeletionRequest).filter(SubjectDeletionRequest.id == request_id).first()
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"This request was already {request.status}")

    vote = db.query(SubjectDeletionVote).filter(
        SubjectDeletionVote.request_id == request.id,
        SubjectDeletionVote.admin_username == user.username,
    ).first()
    if vote is None:
        db.add(SubjectDeletionVote(request_id=request.id, admin_username=user.username, approve=req.approve))
    else:
        vote.approve, vote.decided_at = req.approve, datetime.utcnow()   # an admin may change their mind while it is pending
    db.flush()
    status = _resolve(db, request)
    db.commit()
    message = {
        "pending": "Approved. Waiting for the other admins.",
        "approved": f'Approved. Every admin agreed, so "{request.subject_name}" was deleted.',
        "rejected": f'Rejected. "{request.subject_name}" stays.',
    }[status]
    return {"status": status, "message": message}
