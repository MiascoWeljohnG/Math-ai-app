"""Learning roadmap + study plan (per student) and teacher reminders."""
import math
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from adaptive import mastery_level, practice_kind
from auth import get_current_user, require_teacher_or_admin
from database import get_db
from models import Lesson, LessonCompletion, LessonQuiz, QuizAttempt, Reminder, Subject, User
from school import in_school, shared_subjects, visible_subjects
from routes.subjects_routes import PASS_PERCENT, QUIZ_LENGTH, SECONDS_PER_QUESTION, _display_name

router = APIRouter(prefix="/learning", tags=["learning"])

PLAN_LESSONS = 3        # how many lessons the study plan covers
WORDS_PER_MINUTE = 200  # reading speed used for the time estimate


def _minutes(seconds: float) -> int:
    return max(1, math.ceil(seconds / 60))


# ---------------------------------------------------------------- roadmap + study plan
@router.get("/roadmap")
def roadmap(
    subject_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """For every subject the student can see: its lessons in order with where they stand, plus a short
    study plan for the next few lessons. Built from real completions and quiz attempts, no model call.
    A lesson is done once its quiz is passed (or it was marked complete and has no quiz)."""
    query = db.query(Subject).filter(visible_subjects(user))
    if subject_id is not None:
        query = query.filter(Subject.id == subject_id)
    result = []
    for subject in query.order_by(Subject.id.asc()).all():
        lessons = (db.query(Lesson).filter(Lesson.subject_id == subject.id)
                   .order_by(Lesson.order_index.asc(), Lesson.id.asc()).all())
        ids = [lesson.id for lesson in lessons]
        read = {i for (i,) in db.query(LessonCompletion.lesson_id)
                .filter(LessonCompletion.user_id == user.id, LessonCompletion.lesson_id.in_(ids))}
        difficulty = dict(db.query(LessonQuiz.lesson_id, LessonQuiz.difficulty).filter(LessonQuiz.lesson_id.in_(ids)).all())
        tries: dict[int, dict] = {}   # lesson id -> {attempts, best percent, passed}
        for lesson_id, score, total, passed in (
            db.query(QuizAttempt.lesson_id, QuizAttempt.score, QuizAttempt.total, QuizAttempt.passed)
            .filter(QuizAttempt.user_id == user.id, QuizAttempt.lesson_id.in_(ids))
        ):
            t = tries.setdefault(lesson_id, {"attempts": 0, "best": 0, "passed": False})
            t["attempts"] += 1
            t["best"] = max(t["best"], round(score * 100 / max(total, 1)))
            t["passed"] = t["passed"] or passed

        rows, plan, done = [], [], 0
        previous = None   # (lesson, its level, its reading minutes): what the lesson before this one looked like
        for lesson in lessons:
            t = tries.get(lesson.id, {"attempts": 0, "best": None, "passed": False})
            is_done = t["passed"] or (lesson.id in read and lesson.id not in difficulty and t["attempts"] == 0)
            done += is_done
            status = "done" if is_done else ("upcoming" if any(r["status"] == "next" for r in rows) else "next")
            level = mastery_level(t["attempts"], t["best"], t["passed"])   # see adaptive.py for the rules
            reading = _minutes(len(lesson.content.split()) * 60 / WORDS_PER_MINUTE)
            rows.append({
                "id": lesson.id, "title": lesson.title, "status": status, "read": lesson.id in read,
                "attempts": t["attempts"], "best_percent": t["best"],
                "level": level, "practice": practice_kind(level),
            })
            if not is_done and len(plan) < PLAN_LESSONS:
                quiz_time = _minutes(QUIZ_LENGTH * SECONDS_PER_QUESTION[difficulty.get(lesson.id) or 3])
                practice_href = f"practice.html?subject={subject.id}&lesson={lesson.id}"
                fast_track = level == "new" and lesson.id not in read and previous is not None and previous[1] == "mastered"
                steps = []
                if level == "struggling" and previous is not None:   # behind: go back one lesson first
                    steps.append({
                        "text": f"Review the previous lesson: {previous[0].title}", "minutes": previous[2],
                        "href": f"lessons.html?subject={subject.id}&lesson={previous[0].id}",
                    })
                if t["attempts"]:   # failed before: re-teach first, then an easier practice set, then retry
                    steps.append({"text": "Re-read the lesson and your last quiz breakdown", "minutes": reading})
                    steps.append({"text": "Do the easier practice set", "minutes": 5, "href": practice_href})
                    steps.append({"text": f"Retake the quiz (pass at {PASS_PERCENT}%)", "minutes": quiz_time})
                elif fast_track:   # mastered the last lesson: test out instead of reading
                    steps.append({"text": f"Fast track: take the quiz first and skip the reading if you pass at {PASS_PERCENT}%", "minutes": quiz_time})
                else:
                    if lesson.id not in read:
                        steps.append({"text": "Read the lesson", "minutes": reading})
                    steps.append({"text": f"Take the quiz (pass at {PASS_PERCENT}%)", "minutes": quiz_time})
                plan.append({
                    "lesson_id": lesson.id, "title": lesson.title, "steps": steps,
                    "minutes": sum(s["minutes"] for s in steps), "level": level, "fast_track": fast_track,
                })
            previous = (lesson, level, reading)
        result.append({
            "subject_id": subject.id, "branch": subject.name, "is_personal": subject.owner_user_id is not None,
            "completed": done, "total": len(lessons), "percent": round(done * 100 / len(lessons)) if lessons else 0,
            "lessons": rows, "study_plan": plan,
        })
    return {"subjects": result}


# ---------------------------------------------------------------- rankings
@router.get("/rankings")
def rankings(
    subject_id: Optional[int] = None,
    limit: int = Query(10, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Student ranking for the landing page (students) and the monitor on the teacher page.
    Only the shared branches count; personal subjects stay private. subject_id filters to one branch.
    Ranked by lessons passed, then the average of each lesson's best score, then total time of those
    best attempts. A student outside the top `limit` still gets their own row back as `me`.
    Teachers and admins also get each student's username and attempt count."""
    shared = db.query(Subject).filter(shared_subjects(user)).order_by(Subject.id.asc()).all()   # your school's branches only
    if subject_id is not None and subject_id not in {s.id for s in shared}:
        raise HTTPException(status_code=404, detail="Subject not found")
    lesson_ids = [i for (i,) in db.query(Lesson.id).filter(
        Lesson.subject_id.in_([s.id for s in shared if subject_id in (None, s.id)]))]

    people: dict[int, dict] = {}   # student id -> their user, attempt count and best result per lesson
    for attempt, student in (db.query(QuizAttempt, User).join(User, User.id == QuizAttempt.user_id)
                             .filter(QuizAttempt.lesson_id.in_(lesson_ids), User.role == "user")):
        person = people.setdefault(student.id, {"user": student, "attempts": 0, "lessons": {}})
        person["attempts"] += 1
        percent, seconds = attempt.score * 100 / max(attempt.total, 1), attempt.seconds or 0
        best = person["lessons"].get(attempt.lesson_id)   # [best percent, its seconds, passed any time]
        if best is None:
            person["lessons"][attempt.lesson_id] = [percent, seconds, attempt.passed]
        else:
            if (-percent, seconds) < (-best[0], best[1]):
                best[0], best[1] = percent, seconds
            best[2] = best[2] or attempt.passed

    staff = user.role in ("teacher", "admin")
    table = []
    for person in people.values():
        results = list(person["lessons"].values())
        row = {
            "name": _display_name(person["user"]),
            "lessons_passed": sum(1 for r in results if r[2]),
            "average_percent": round(sum(r[0] for r in results) / len(results)),
            "seconds": sum(r[1] for r in results),
            "you": person["user"].id == user.id,
        }
        if staff:
            row["username"], row["attempts"] = person["user"].username, person["attempts"]
        table.append(row)
    table.sort(key=lambda r: (-r["lessons_passed"], -r["average_percent"], r["seconds"], r["name"].lower()))
    for rank, row in enumerate(table, 1):
        row["rank"] = rank
    return {
        "branches": [{"id": s.id, "name": s.name} for s in shared],
        "entries": table[:limit],
        "me": next((r for r in table[limit:] if r["you"]), None),
    }


# ---------------------------------------------------------------- reminders
class ReminderRequest(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    student_username: Optional[str] = None   # None = every student
    due_date: Optional[date] = None


def _serialize_reminder(r: Reminder) -> dict:
    return {
        "id": r.id,
        "message": r.message,
        "created_by": r.created_by,
        "to": r.student_username or "Everyone",
        "due_date": r.due_date.isoformat() if r.due_date else None,
        "overdue": bool(r.due_date and r.due_date < date.today()),
        "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
    }


@router.post("/reminders")
def create_reminder(
    req: ReminderRequest,
    user: User = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Write a message for the reminder")
    if req.student_username and not db.query(User).filter(
        User.username == req.student_username, User.role == "user", in_school(User.school_id, user.school_id),
    ).first():
        raise HTTPException(status_code=404, detail="Student not found")
    reminder = Reminder(
        message=message, created_by=user.username,
        student_username=req.student_username or None, due_date=req.due_date, school_id=user.school_id,
    )
    db.add(reminder)
    db.commit()
    return _serialize_reminder(reminder)


@router.get("/reminders")
def list_reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Students: the reminders for everyone plus the ones addressed to them. Teachers: the ones they wrote.
    Admins: all of them. Soonest due date first; no date goes last."""
    query = db.query(Reminder)
    if user.role == "user":
        query = query.filter(
            in_school(Reminder.school_id, user.school_id),   # "everyone" means everyone at the author's school
            or_(Reminder.student_username.is_(None), Reminder.student_username == user.username),
        )
    elif user.role == "teacher":
        query = query.filter(Reminder.created_by == user.username)
    rows = sorted(query.all(), key=lambda r: (r.due_date is None, r.due_date or date.max, -r.id))
    return [_serialize_reminder(r) for r in rows]


@router.delete("/reminders/{reminder_id}")
def delete_reminder(
    reminder_id: int,
    user: User = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
):
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if user.role != "admin" and reminder.created_by != user.username:
        raise HTTPException(status_code=403, detail="You can only delete your own reminders")
    db.delete(reminder)
    db.commit()
    return {"message": "Reminder deleted."}
