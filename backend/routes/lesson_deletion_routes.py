"""Deleting a published lesson. A teacher can only ASK to delete a lesson; the admin of their school decides.
Approving deletes the lesson with its quiz, practice sets and students' completion records; rejecting keeps it.
Drafts (lessons nobody but staff can see yet) are not covered: they can still be thrown away directly.
Everything is limited to the requester's own school, and each request and decision goes into the audit log."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_school_admin, require_teacher
from database import get_db
from models import AuditLog, Lesson, LessonCompletion, LessonDeletionRequest, Subject, User
from notifications import notify_admins
from routes.subjects_routes import delete_lesson_cascade
from school import shared_subjects

router = APIRouter(prefix="/lesson-deletions", tags=["lesson-deletions"])

REJECTION_SHOWN_FOR = timedelta(days=14)   # how long a teacher keeps seeing "the admin kept this lesson"


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() + "Z" if moment else None


def _target(request: LessonDeletionRequest) -> str:
    """How the audit log names the lesson: its title and the subject it lived in."""
    return f'{request.lesson_title} ({request.subject_name})'


class LessonDeletionBody(BaseModel):
    subject_id: int
    lesson_id: int
    reason: Optional[str] = Field(default=None, max_length=300)


@router.post("")
def request_lesson_deletion(req: LessonDeletionBody, user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == req.subject_id, shared_subjects(user)).first()
    lesson = db.query(Lesson).filter(Lesson.id == req.lesson_id, Lesson.subject_id == req.subject_id).first() if subject else None
    if subject is None or lesson is None:   # another school's lesson looks like it does not exist
        raise HTTPException(status_code=404, detail="Lesson not found")
    if lesson.status != "published":
        raise HTTPException(status_code=400, detail="Only published lessons need approval. A draft can be deleted directly.")
    if db.query(LessonDeletionRequest).filter(LessonDeletionRequest.lesson_id == lesson.id, LessonDeletionRequest.status == "pending").first():
        raise HTTPException(status_code=409, detail="A deletion request for this lesson is already waiting for the school admin")

    reason = (req.reason or "").strip() or None
    request = LessonDeletionRequest(
        lesson_id=lesson.id, lesson_title=lesson.title, subject_id=subject.id, subject_name=subject.name,
        requested_by=user.username, school_id=user.school_id, reason=reason,
    )
    db.add(request)
    db.add(AuditLog(actor=user.username, school_id=user.school_id, action="lesson.delete.request", target=_target(request), detail=reason))
    notify_admins(db, "lesson_deletion_request", "Lesson deletion requested",
                  f'@{user.username} asked to delete the lesson "{lesson.title}" in "{subject.name}".', school_id=user.school_id)
    db.commit()
    return {"status": "pending", "message": f'Request sent. "{lesson.title}" will be deleted once your school admin approves.', "request_id": request.id}


@router.get("/mine")
def my_requests(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """What happened to this teacher's requests: the ones still waiting, and recently declined ones, so the
    lesson list can say so next to the lesson."""
    since = datetime.utcnow() - REJECTION_SHOWN_FOR
    rows = db.query(LessonDeletionRequest).filter(LessonDeletionRequest.requested_by == user.username).order_by(LessonDeletionRequest.id.asc()).all()
    latest = {}
    for row in rows:   # the newest request per lesson wins (a lesson can be asked about again after a decline)
        latest[row.lesson_id] = row
    return [
        {"lesson_id": lesson_id, "status": row.status}
        for lesson_id, row in latest.items()
        if row.status == "pending" or (row.status == "rejected" and row.resolved_at and row.resolved_at >= since)
    ]


@router.get("")
def list_requests(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """The requests waiting for this school admin's answer, oldest first."""
    rows = (
        db.query(LessonDeletionRequest)
        .filter(LessonDeletionRequest.status == "pending", LessonDeletionRequest.school_id == user.school_id)
        .order_by(LessonDeletionRequest.created_at.asc(), LessonDeletionRequest.id.asc())
        .all()
    )
    names = {u.username: u.person_name for u in db.query(User).filter(User.school_id == user.school_id)}
    result, changed = [], False
    for row in rows:
        lesson = db.query(Lesson).filter(Lesson.id == row.lesson_id).first()
        if lesson is None:   # the lesson is already gone (its subject or the admin deleted it): nothing left to decide
            row.status, row.resolved_at, changed = "approved", datetime.utcnow(), True
            continue
        result.append({
            "id": row.id,
            "lesson_id": row.lesson_id,
            "lesson_title": lesson.title,
            "subject_id": row.subject_id,
            "subject_name": row.subject_name,
            "requested_by": row.requested_by,
            "requested_by_name": names.get(row.requested_by, ""),
            "reason": row.reason,
            "created_at": _iso(row.created_at),
            "completions": db.query(func.count(LessonCompletion.id)).filter(LessonCompletion.lesson_id == row.lesson_id).scalar() or 0,
        })
    if changed:
        db.commit()
    return result


class Decision(BaseModel):
    approve: bool


@router.post("/{request_id}/decision")
def decide(request_id: int, req: Decision, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    request = db.query(LessonDeletionRequest).filter(LessonDeletionRequest.id == request_id, LessonDeletionRequest.school_id == user.school_id).first()
    if request is None:   # another school's request looks like it does not exist
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"This request was already {request.status}")

    title = request.lesson_title
    if req.approve:
        lesson = db.query(Lesson).filter(Lesson.id == request.lesson_id).first()
        if lesson is not None:
            delete_lesson_cascade(db, lesson)
        message = f'Approved. "{title}" was deleted.'
    else:
        message = f'Rejected. "{title}" stays.'
    request.status = "approved" if req.approve else "rejected"
    request.resolved_at, request.decided_by = datetime.utcnow(), user.username
    db.add(AuditLog(actor=user.username, school_id=user.school_id, action="lesson.delete.approve" if req.approve else "lesson.delete.reject", target=_target(request)))
    db.commit()
    return {"status": request.status, "message": message}
