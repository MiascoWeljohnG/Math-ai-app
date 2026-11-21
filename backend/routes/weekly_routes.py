"""Weekly pacing, run by the school admin: which week each lesson of a subject belongs to, and how the school's
"current week" moves (by itself every 7 days, or only when the admin says). Students see the result as coloured lessons
(see weekly.py and subjects_routes.list_lessons). Everything is limited to the admin's own school: the school comes
from the account, never from the request."""
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import completion
import weekly
from auth import require_school_admin
from database import get_db
from models import ACTIVE, AuditLog, Lesson, Subject, User, WeeklySchedule
from school import in_school, shared_subjects

router = APIRouter(prefix="/school-admin/weekly", tags=["weekly"])


def _subject_or_404(db: Session, subject_id: int, user: User) -> Subject:
    subject = db.query(Subject).filter(Subject.id == subject_id, shared_subjects(user)).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


def _schedule(db: Session, subject: Subject) -> Optional[WeeklySchedule]:
    return db.query(WeeklySchedule).filter(WeeklySchedule.subject_id == subject.id).first()


def _published(db: Session, subject: Subject) -> list[Lesson]:
    return (db.query(Lesson).filter(Lesson.subject_id == subject.id, Lesson.status == "published")
            .order_by(Lesson.order_index.asc(), Lesson.id.asc()).all())


def _log(db: Session, user: User, action: str, subject: Subject, detail: str = "") -> None:
    db.add(AuditLog(actor=user.username, school_id=user.school_id, action=action, target=subject.name, detail=detail or None))


def _state(db: Session, subject: Subject, user: User) -> dict:
    """Everything the admin page draws for one subject."""
    schedule = _schedule(db, subject)
    lessons = _published(db, subject)
    now_week = weekly.current_week(schedule) if schedule else None

    students = db.query(func.count(User.id)).filter(
        User.role == "user", User.status == ACTIVE, in_school(User.school_id, user.school_id)).scalar() or 0
    people = [i for (i,) in db.query(User.id).filter(User.role == "user", User.status == ACTIVE, in_school(User.school_id, user.school_id))]
    finished: dict[int, int] = {}   # lesson id -> students who finished it (completion.py: passed its quiz, or no quiz and marked complete)
    for _, lesson_id in completion.finished_pairs(db, [l.id for l in lessons], people):
        finished[lesson_id] = finished.get(lesson_id, 0) + 1

    rows = []
    for lesson in lessons:
        dates = weekly.week_dates(schedule, lesson.week_number) if schedule and lesson.week_number else None
        done = finished.get(lesson.id, 0)
        rows.append({
            "id": lesson.id, "title": lesson.title, "week_number": lesson.week_number,
            "week_start": dates[0].isoformat() if dates else None, "week_end": dates[1].isoformat() if dates else None,
            "completed": done,
            # students who should have finished it by now (its week has started or passed) but have not
            "behind": max(0, students - done) if (schedule and schedule.enabled and lesson.week_number
                                                   and now_week is not None and lesson.week_number < now_week) else 0,
        })
    return {
        "subject": {"id": subject.id, "name": subject.name},
        "students": students,
        "schedule": None if schedule is None else {
            "enabled": schedule.enabled, "mode": schedule.mode,
            "start_date": schedule.start_date.isoformat() if schedule.start_date else None,
            "manual_week": schedule.manual_week, "current_week": now_week,
        },
        "today": date.today().isoformat(),
        "lessons": rows,
    }


@router.get("")
def list_weekly_subjects(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """The school's shared subjects, each with whether weekly pacing is on and which week it is."""
    out = []
    for subject in db.query(Subject).filter(shared_subjects(user)).order_by(Subject.id.asc()).all():
        schedule = _schedule(db, subject)
        out.append({
            "id": subject.id, "name": subject.name,
            "enabled": bool(schedule and schedule.enabled),
            "mode": schedule.mode if schedule else None,
            "current_week": weekly.current_week(schedule) if schedule else None,
        })
    return out


@router.get("/{subject_id}")
def get_weekly(subject_id: int, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    return _state(db, _subject_or_404(db, subject_id, user), user)


class ScheduleRequest(BaseModel):
    enabled: bool = True                      # False = back to plain lesson-by-lesson unlocking (the plan is kept)
    mode: Literal["auto", "manual"] = "auto"  # auto: the week moves by itself every 7 days. manual: it stays until you move it
    start_date: Optional[date] = None         # first day of week 1 (auto)
    manual_week: Optional[int] = Field(default=None, ge=0, le=weekly.MAX_WEEK)   # the week it stays on (manual)


@router.put("/{subject_id}/schedule")
def save_schedule(subject_id: int, req: ScheduleRequest, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    subject = _subject_or_404(db, subject_id, user)
    today = date.today()
    row = _schedule(db, subject)
    if row is None:
        row = WeeklySchedule(subject_id=subject.id, school_id=user.school_id, mode=weekly.AUTO, start_date=today, manual_week=1)
        db.add(row)
    if req.mode == weekly.MANUAL:
        if row.mode == weekly.AUTO:
            weekly.hold(row, today)               # "stay": freeze the week it is on right now
        if req.manual_week is not None:
            row.manual_week = req.manual_week
    else:
        if row.mode == weekly.MANUAL:
            weekly.resume(row, today, req.start_date)
        elif req.start_date is not None:
            row.start_date = req.start_date
        if row.start_date is None:
            row.start_date = today
    row.enabled = req.enabled
    row.updated_by, row.school_id = user.username, user.school_id
    _log(db, user, "weekly.schedule", subject, f"{'on' if row.enabled else 'off'}, {row.mode}")
    db.commit()
    return _state(db, subject, user)


class WeekMove(BaseModel):
    action: Literal["next", "previous"]


@router.post("/{subject_id}/week")
def move_week(subject_id: int, req: WeekMove, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """Advance to the next week (or step back one) right now, whichever mode the schedule is in."""
    subject = _subject_or_404(db, subject_id, user)
    row = _schedule(db, subject)
    if row is None:
        raise HTTPException(status_code=409, detail="Turn on weekly pacing for this subject first.")
    week = weekly.move_week(row, 1 if req.action == "next" else -1)
    row.updated_by = user.username
    _log(db, user, "weekly.week", subject, f"now on week {week}")
    db.commit()
    return _state(db, subject, user)


class LessonWeek(BaseModel):
    week_number: Optional[int] = Field(default=None, ge=1, le=weekly.MAX_WEEK)   # None takes the lesson out of the plan


@router.put("/{subject_id}/lessons/{lesson_id}")
def set_lesson_week(subject_id: int, lesson_id: int, req: LessonWeek, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """Make one lesson the task of a week (or take it out of the weekly plan)."""
    subject = _subject_or_404(db, subject_id, user)
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.subject_id == subject.id).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if lesson.status != "published":
        raise HTTPException(status_code=409, detail="Approve this draft lesson before putting it in the weekly plan.")
    lesson.week_number = req.week_number
    _log(db, user, "weekly.lesson", subject, f"{lesson.title}: " + (f"week {req.week_number}" if req.week_number else "removed from the plan"))
    db.commit()
    return _state(db, subject, user)


class AutoAssign(BaseModel):
    per_week: int = Field(default=1, ge=1, le=10)
    start_week: int = Field(default=1, ge=1, le=weekly.MAX_WEEK)
    overwrite: bool = False   # False: only lessons that have no week yet are placed; True: redo the whole plan


@router.post("/{subject_id}/auto-assign")
def auto_assign(subject_id: int, req: AutoAssign, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """Spread the lessons over the weeks in course order, `per_week` lessons to a week."""
    subject = _subject_or_404(db, subject_id, user)
    placed = weekly.auto_assign(_published(db, subject), req.per_week, req.start_week, req.overwrite)
    _log(db, user, "weekly.auto", subject, f"{placed} lesson(s), {req.per_week} per week from week {req.start_week}")
    db.commit()
    return _state(db, subject, user)
