from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Lesson, LessonCompletion, Subject, User
from school import visible_subjects

# The four branches shown on the landing page. The teacher dashboard has one
# column per branch, in this order.
BRANCHES = ["Algebra", "Geometry", "Statistics", "Calculus"]

# What a file can be tagged as when uploaded. "General" covers material that
# doesn't belong to one branch (and every file uploaded before tagging existed).
UPLOAD_BRANCHES = BRANCHES + ["General"]


def progress_for_user(db: Session, user: User) -> list[dict]:
    """Real progress: lessons this user marked complete / all lessons, per subject
    they can see (their school's shared subjects, plus their own personal ones)."""
    subjects = (
        db.query(Subject)
        .filter(visible_subjects(user))
        .order_by(Subject.id.asc())
        .all()
    )
    totals = dict(db.query(Lesson.subject_id, func.count(Lesson.id)).group_by(Lesson.subject_id).all())
    done = dict(
        db.query(Lesson.subject_id, func.count(LessonCompletion.id))
        .join(LessonCompletion, LessonCompletion.lesson_id == Lesson.id)
        .filter(LessonCompletion.user_id == user.id)
        .group_by(Lesson.subject_id)
        .all()
    )
    result = []
    for subject in subjects:
        total = totals.get(subject.id, 0)
        completed = done.get(subject.id, 0)
        result.append({
            "subject_id": subject.id,
            "branch": subject.name,
            "is_personal": subject.owner_user_id is not None,
            "completed": completed,
            "total": total,
            "percent": round(completed * 100 / total) if total else 0,
        })
    return result
