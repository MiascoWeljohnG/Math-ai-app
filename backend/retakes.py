"""Quiz locks. A quiz that was ended for violations locks that lesson's quiz for that student until a teacher
approves their feedback. The rules live here so the quiz routes and the teacher routes agree on them.

    violation -> locked  --student sends feedback-->  pending  --teacher-->  approved (one retake) -> used
                                                                        \\-->  rejected (new feedback allowed)
"""
from datetime import datetime

from sqlalchemy.orm import Session

from models import Lesson, QuizRetakeRequest, Subject, User
from notifications import notify_teachers

LOCKED, PENDING, APPROVED, REJECTED, USED = "locked", "pending", "approved", "rejected", "used"
BLOCKING = (LOCKED, PENDING, REJECTED)   # the student cannot open or submit the quiz in these states
MIN_FEEDBACK_CHARS = 10


def open_row(db: Session, user_id: int, lesson_id: int) -> QuizRetakeRequest | None:
    """The newest row that is not used up, or None."""
    return (db.query(QuizRetakeRequest)
            .filter(QuizRetakeRequest.user_id == user_id, QuizRetakeRequest.lesson_id == lesson_id,
                    QuizRetakeRequest.status != USED)
            .order_by(QuizRetakeRequest.id.desc()).first())


def blocking_lock(db: Session, user: User, lesson_id: int) -> QuizRetakeRequest | None:
    """The lock that stops this student from taking this lesson's quiz, or None. Only students are ever locked:
    a teacher previewing a quiz is not recorded and cannot be blocked."""
    if user.role != "user":
        return None
    row = open_row(db, user.id, lesson_id)
    return row if row is not None and row.status in BLOCKING else None


def lock_payload(row: QuizRetakeRequest | None) -> dict | None:
    """What the quiz page needs to show the lock (no ids, no other students)."""
    if row is None:
        return None
    return {
        "status": row.status,
        "violations": row.violations,
        "feedback": row.feedback or "",
        "teacher_note": row.teacher_note or "",
        "can_request": row.status in (LOCKED, REJECTED),
    }


def consume_approval(db: Session, user: User, lesson_id: int) -> None:
    """The approved retake is being taken: it is spent. Only adds to the session; the caller commits."""
    row = open_row(db, user.id, lesson_id)
    if row is not None and row.status == APPROVED:
        row.status = USED


def lock_for_violations(db: Session, student: User, lesson: Lesson, subject: Subject, violations: int) -> QuizRetakeRequest:
    """The quiz was ended for violations: lock it and tell the school's teachers. Adds to the session; the caller commits."""
    consume_approval(db, student, lesson.id)   # a retake that also ended in violations is spent, and locks again
    row = QuizRetakeRequest(user_id=student.id, lesson_id=lesson.id, school_id=student.school_id,
                            violations=violations, status=LOCKED)
    db.add(row)
    notify_teachers(
        db, student.school_id, "quiz_violation", "Student ended a quiz for violations",
        f'{student.display_name} (@{student.username}) left the quiz {violations} times in "{lesson.title}" ({subject.name}). '
        "The quiz was submitted and is locked for them until you approve a retake.",
    )
    return row


def send_request(db: Session, student: User, row: QuizRetakeRequest, feedback: str, lesson: Lesson) -> None:
    """The student explains themselves and asks to retake. Adds to the session; the caller commits."""
    row.status, row.feedback, row.teacher_note = PENDING, feedback, None
    row.requested_at = datetime.utcnow()
    notify_teachers(
        db, student.school_id, "retake_request", "Retake requested",
        f'{student.display_name} (@{student.username}) asks to retake "{lesson.title}": {feedback[:160]}'
        + ("..." if len(feedback) > 160 else ""),
    )
