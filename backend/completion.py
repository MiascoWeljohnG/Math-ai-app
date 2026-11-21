"""What "completed" means for a student, in one place. The lessons page, the locks and weekly colours, the roadmap, the home
progress bars and the school admin's "students finished" counts all ask here, so they can never disagree.

In a shared subject a student finishes a lesson by passing its quiz (80%). A lesson that has no quiz is finished by being
marked complete. A completion record on a lesson whose quiz was never passed does not count (older versions of the app let a
click complete any lesson, and those records are still in the database). Staff, and a student's own personal subject, are not
gated: there a click is enough.
"""
from sqlalchemy.orm import Session

from models import LessonCompletion, LessonQuiz, QuizAttempt

STAFF_ROLES = ("teacher", "school_admin", "admin")


def quiz_decides(subject, user) -> bool:
    """True when `user` has to pass the quiz to finish a lesson of `subject` (a student in a shared subject)."""
    return subject.owner_user_id is None and user.role not in STAFF_ROLES


def finished_pairs(db: Session, lesson_ids, user_ids) -> set[tuple[int, int]]:
    """{(user_id, lesson_id)} the quiz rule above counts as finished. Use it for shared subjects only."""
    lesson_ids, user_ids = list(lesson_ids), list(user_ids)
    if not lesson_ids or not user_ids:
        return set()
    where_att = (QuizAttempt.lesson_id.in_(lesson_ids), QuizAttempt.user_id.in_(user_ids))
    passed = {(u, l) for u, l in db.query(QuizAttempt.user_id, QuizAttempt.lesson_id).filter(*where_att, QuizAttempt.passed.is_(True))}
    marked = {(u, l) for u, l in db.query(LessonCompletion.user_id, LessonCompletion.lesson_id).filter(
        LessonCompletion.lesson_id.in_(lesson_ids), LessonCompletion.user_id.in_(user_ids))}
    unproven = marked - passed
    if not unproven:
        return passed
    maybe = {l for _, l in unproven}
    has_quiz = {l for (l,) in db.query(LessonQuiz.lesson_id).filter(LessonQuiz.lesson_id.in_(maybe))}
    tried = {(u, l) for u, l in db.query(QuizAttempt.user_id, QuizAttempt.lesson_id).filter(
        QuizAttempt.lesson_id.in_(maybe), QuizAttempt.user_id.in_(user_ids))}
    return passed | {(u, l) for u, l in unproven if l not in has_quiz and (u, l) not in tried}


def finished_ids(db: Session, user, subject, lesson_ids) -> set[int]:
    """The lessons of `subject` that `user` has finished (see the module docstring)."""
    lesson_ids = list(lesson_ids)
    if not lesson_ids:
        return set()
    if quiz_decides(subject, user):
        return {l for _, l in finished_pairs(db, lesson_ids, [user.id])}
    return {l for (l,) in db.query(LessonCompletion.lesson_id).filter(
        LessonCompletion.user_id == user.id, LessonCompletion.lesson_id.in_(lesson_ids))}
