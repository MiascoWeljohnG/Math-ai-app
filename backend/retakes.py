"""Quiz locks. A quiz that was ended for violations locks that lesson's quiz for that student until a teacher
approves their feedback. The rules live here so the quiz routes and the teacher routes agree on them.

    3 practice tries used up -> locked  --student sends feedback-->  pending  --teacher-->  approved (one retake) -> used
                                                                                       \\-->  rejected (new feedback allowed)

A quiz ended for violations does NOT lock any more: it only tells the teachers the student may be struggling
(flag_struggling). The lock comes from using up the practice tries.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from models import Lesson, PracticeSet, QuizRetakeRequest, Subject, User
from notifications import notify_teachers

LOCKED, PENDING, APPROVED, REJECTED, USED = "locked", "pending", "approved", "rejected", "used"
BLOCKING = (LOCKED, PENDING, REJECTED)   # the student cannot open or submit the quiz in these states
MIN_FEEDBACK_CHARS = 10
MAX_PRACTICE_TRIES = 3   # practice sets a student may use on one lesson before a teacher has to approve a retake


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


def flag_struggling(db: Session, student: User, lesson: Lesson, subject: Subject, violations: int, percent: int) -> None:
    """The quiz was ended for violations. That is not punished with a lock: the quiz was submitted and counts as a
    try, and the school's teachers get a hint that this student may really be struggling. The caller commits."""
    consume_approval(db, student, lesson.id)   # a retake that ended this way is spent
    notify_teachers(
        db, student.school_id, "quiz_violation", "Student may be struggling",
        f'{student.display_name} (@{student.username}) left the quiz {violations} times in "{lesson.title}" ({subject.name}) '
        f"and it was submitted automatically at {percent}%. This often means they are really struggling with the lesson, "
        "so a quick check-in or some extra help could be worth more than a penalty.",
    )


def practice_tries(db: Session, user_id: int, lesson_id: int) -> int:
    """Practice sets this student has used on this lesson since their last approved retake."""
    row = db.query(PracticeSet).filter(PracticeSet.user_id == user_id, PracticeSet.lesson_id == lesson_id).first()
    return 0 if row is None else (1 if row.tries is None else row.tries)   # NULL = a row from before tries existed


def reset_practice_tries(db: Session, user_id: int, lesson_id: int) -> None:
    """A teacher approved a retake: the student starts again with a fresh set of tries. The caller commits."""
    row = db.query(PracticeSet).filter(PracticeSet.user_id == user_id, PracticeSet.lesson_id == lesson_id).first()
    if row is not None:
        row.tries = 0


def lock_for_tries(db: Session, student: User, lesson: Lesson, subject: Subject) -> QuizRetakeRequest | None:
    """All practice tries are used and the lesson is still not passed: the quiz needs a teacher's approval to be
    retaken, and the teachers are told. Does nothing if a lock or request is already open. The caller commits."""
    existing = open_row(db, student.id, lesson.id)
    if existing is not None:
        return existing
    row = QuizRetakeRequest(user_id=student.id, lesson_id=lesson.id, school_id=student.school_id, violations=0, status=LOCKED)
    db.add(row)
    notify_teachers(
        db, student.school_id, "quiz_violation", "Student used all practice tries",
        f'{student.display_name} (@{student.username}) used all {MAX_PRACTICE_TRIES} practice tries on "{lesson.title}" '
        f"({subject.name}) without passing the quiz. They can retake it only if you approve, and may really be struggling.",
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
