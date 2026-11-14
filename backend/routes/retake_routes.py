"""Quiz retake requests: a student whose quiz was ended for violations is locked out of it (see retakes.py) until a
teacher or the school admin of their school approves their feedback."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import retakes
from auth import require_staff
from database import get_db
from models import AuditLog, Lesson, QuizRetakeRequest, Subject, User
from school import in_school

router = APIRouter(prefix="/retake-requests", tags=["retake-requests"])
KEEP_DECIDED = 30   # decided and waiting-for-feedback rows shown below the pending ones


def _iso(stamp: datetime | None) -> str | None:
    return stamp.isoformat() + "Z" if stamp else None   # UTC; Z lets the browser localise it


def _mine(db: Session, user: User):
    """Requests of the staff member's own school, joined with the student, lesson and subject for display."""
    return (db.query(QuizRetakeRequest, User, Lesson, Subject)
            .join(User, User.id == QuizRetakeRequest.user_id)
            .join(Lesson, Lesson.id == QuizRetakeRequest.lesson_id)
            .join(Subject, Subject.id == Lesson.subject_id)
            .filter(in_school(QuizRetakeRequest.school_id, user.school_id)))


def _row(request: QuizRetakeRequest, student: User, lesson: Lesson, subject: Subject) -> dict:
    return {
        "id": request.id, "status": request.status, "violations": request.violations,
        "student": student.display_name, "username": student.username,
        "lesson": lesson.title, "subject": subject.name,
        "feedback": request.feedback or "", "teacher_note": request.teacher_note or "",
        "ended_at": _iso(request.created_at), "requested_at": _iso(request.requested_at),
        "decided_at": _iso(request.decided_at), "decided_by": request.decided_by,
    }


@router.get("")
def list_requests(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Pending requests first (they need an answer), then the latest others. Spent retakes are history and stay out."""
    query = _mine(db, user).filter(QuizRetakeRequest.status != retakes.USED)
    pending = query.filter(QuizRetakeRequest.status == retakes.PENDING).order_by(QuizRetakeRequest.requested_at.asc()).all()
    others = (query.filter(QuizRetakeRequest.status != retakes.PENDING)
              .order_by(QuizRetakeRequest.id.desc()).limit(KEEP_DECIDED).all())
    return {"pending": len(pending), "items": [_row(*parts) for parts in [*pending, *others]]}


class DecisionRequest(BaseModel):
    approve: bool
    note: Optional[str] = Field(default=None, max_length=300)   # shown to the student; worth writing when rejecting


@router.post("/{request_id}/decision")
def decide(request_id: int, req: DecisionRequest, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    parts = _mine(db, user).filter(QuizRetakeRequest.id == request_id).first()   # another school's request is a 404
    if parts is None:
        raise HTTPException(status_code=404, detail="Request not found")
    request, student, lesson, subject = parts
    if request.status != retakes.PENDING:
        raise HTTPException(status_code=409, detail="This request was already decided or the student hasn't sent feedback yet.")
    request.status = retakes.APPROVED if req.approve else retakes.REJECTED
    request.teacher_note = (req.note or "").strip() or None
    request.decided_by, request.decided_at = user.username, datetime.utcnow()
    db.add(AuditLog(
        actor=user.username, school_id=user.school_id,
        action="quiz.retake.approve" if req.approve else "quiz.retake.reject",
        target=f"@{student.username}: {lesson.title} ({subject.name})",
    ))
    db.commit()
    return {"message": f"Retake {'approved' if req.approve else 'rejected'} for {student.display_name}."}
