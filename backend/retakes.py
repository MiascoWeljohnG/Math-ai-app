"""Quiz locks. A quiz that was ended for violations, or whose practice tries are used up, locks that lesson's quiz for
that student until a teacher approves their feedback. The rules live here so the quiz routes and the teacher routes
agree on them.

    ended for violations / 3 practice tries used up -> locked  --student sends feedback-->  pending
                                  --teacher-->  approved (one retake) -> used
                                          \\-->  rejected (new feedback allowed)

Violations are counted by the server as well as by the quiz page (QuizSession), so reloading the page cannot reset them:
every violation is reported as it happens, and reloading or closing the page mid-quiz counts as one more.
"""
import math
from datetime import datetime

from sqlalchemy.orm import Session

from models import Lesson, PracticeSet, QuizRetakeRequest, QuizSession, Subject, User
from notifications import notify_teachers

LOCKED, PENDING, APPROVED, REJECTED, USED = "locked", "pending", "approved", "rejected", "used"
BLOCKING = (LOCKED, PENDING, REJECTED)   # the student cannot open or submit the quiz in these states
MIN_FEEDBACK_CHARS = 10
MAX_VIOLATIONS = 3       # violations (leaving the tab, minimizing, shrinking the window, reloading) before the quiz is ended
SESSION_GRACE = 20       # seconds past the time limit before an attempt that was never submitted counts as abandoned
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


def lock_for_violations(db: Session, student: User, lesson: Lesson, subject: Subject, violations: int,
                        percent: int | None = None) -> QuizRetakeRequest:
    """The quiz was ended for violations: it is locked for this student until a teacher approves a retake, and the
    school's teachers are told. `percent` is the score of a submitted quiz; None means it was never submitted (the page
    was reloaded or closed). A retake that ended this way is spent. The caller commits."""
    existing = open_row(db, student.id, lesson.id)
    if existing is not None and existing.status == APPROVED:
        existing.status = USED
    elif existing is not None:
        return existing   # already locked or waiting for a teacher
    row = QuizRetakeRequest(user_id=student.id, lesson_id=lesson.id, school_id=student.school_id,
                            violations=violations, status=LOCKED)
    db.add(row)
    outcome = (f"and it was submitted automatically at {percent}%." if percent is not None
               else "and the quiz page was reloaded or closed before it was submitted.")
    notify_teachers(
        db, student.school_id, "quiz_violation", "Quiz ended for violations",
        f'{student.display_name} (@{student.username}) was locked out of "{lesson.title}" ({subject.name}) after '
        f"{violations} violations {outcome} They cannot retake it unless you approve it under Quiz retake requests. "
        "They may also be struggling with the lesson, so a quick check-in could help.",
    )
    return row


# ---------------------------------------------------------------- attempts in progress (QuizSession)
def open_session(db: Session, user_id: int, lesson_id: int) -> QuizSession | None:
    """The student's attempt on this lesson that has not been submitted or ended, or None."""
    return (db.query(QuizSession)
            .filter(QuizSession.user_id == user_id, QuizSession.lesson_id == lesson_id, QuizSession.finished.is_(False))
            .order_by(QuizSession.id.desc()).first())


def seconds_left(session: QuizSession) -> int:
    return max(0, math.ceil(session.time_limit - (datetime.utcnow() - session.started_at).total_seconds()))


def start_session(db: Session, student: User, lesson: Lesson, time_limit: int) -> QuizSession:
    """The student pressed Start. An attempt that is still open (the page was reloaded) is resumed: its violations
    and its clock carry over, so reloading is no way to get a fresh timer. The caller commits."""
    session = open_session(db, student.id, lesson.id)
    if session is None:
        session = QuizSession(user_id=student.id, lesson_id=lesson.id, started_at=datetime.utcnow(), violations=0)
        db.add(session)
    session.time_limit, session.in_page = time_limit, True
    return session


def record_violation(db: Session, student: User, lesson: Lesson) -> QuizSession | None:
    """The quiz page reports one violation as it happens. The caller commits."""
    session = open_session(db, student.id, lesson.id)
    if session is not None and session.in_page:
        session.violations += 1
    return session


def settle_left_page(db: Session, student: User, lesson: Lesson, subject: Subject) -> QuizRetakeRequest | None:
    """The quiz was opened while an attempt was still running on another page: that page was reloaded, closed or
    left for good. That is one more violation. At MAX_VIOLATIONS, or when the time ran out with nothing submitted,
    the attempt ends and the quiz locks; otherwise the student resumes with the violations they have. The caller commits."""
    session = open_session(db, student.id, lesson.id)
    if session is None or not session.in_page:
        return None   # nothing is running, or the reload was already counted and the student has not resumed yet
    session.in_page = False
    session.violations += 1
    elapsed = (datetime.utcnow() - session.started_at).total_seconds()
    if session.violations >= MAX_VIOLATIONS or elapsed > session.time_limit + SESSION_GRACE:
        session.finished = True
        return lock_for_violations(db, student, lesson, subject, session.violations)
    return None


def finish_session(db: Session, user_id: int, lesson_id: int) -> None:
    """The attempt was submitted. The caller commits."""
    session = open_session(db, user_id, lesson_id)
    if session is not None:
        session.finished = True


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
