from sqlalchemy import func
from sqlalchemy.orm import Session

import completion
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
    lessons_of: dict[int, list[int]] = {}
    for lesson_id, subject_id in db.query(Lesson.id, Lesson.subject_id).filter(Lesson.subject_id.in_([s.id for s in subjects])):
        lessons_of.setdefault(subject_id, []).append(lesson_id)
    # what counts as completed is decided in completion.py (so this agrees with the lessons page and the roadmap)
    done = {s.id: len(completion.finished_ids(db, user, s, lessons_of.get(s.id, []))) for s in subjects}
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
