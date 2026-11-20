"""Weekly pacing for a shared subject, in one place (no database or web code here, so it is easy to test).

The school admin puts each lesson in a week of the school's schedule (Lesson.week_number) and decides how the schedule
moves (WeeklySchedule). A student then sees every lesson in one of four states:

    done     completed: the student passed its quiz (green)
    current  this week's task (blue)
    behind   an earlier week's task they have not finished, so they are behind the pace (red)
    closed   the school has not opened it yet: no week, or a week that has not started (gray). Students cannot open it.
"""
from datetime import date, timedelta
from typing import Optional

AUTO, MANUAL = "auto", "manual"
DONE, CURRENT, BEHIND, CLOSED = "done", "current", "behind", "closed"
MAX_WEEK = 60   # a school year is well inside this; it only stops typos like week 9999


def current_week(schedule, today: Optional[date] = None) -> int:
    """The week the school is on now. 0 means nothing is open yet (an auto schedule whose first day has not come)."""
    today = today or date.today()
    if schedule.mode == MANUAL:
        return max(0, schedule.manual_week or 0)
    if schedule.start_date is None or today < schedule.start_date:
        return 0
    return (today - schedule.start_date).days // 7 + 1


def week_dates(schedule, week: int) -> Optional[tuple[date, date]]:
    """First and last day of a week, when the calendar decides it (auto mode). Manual weeks have no dates."""
    if schedule.mode != AUTO or schedule.start_date is None or week < 1:
        return None
    first = schedule.start_date + timedelta(days=7 * (week - 1))
    return first, first + timedelta(days=6)


def pace(lesson_week: Optional[int], now_week: int, completed: bool) -> str:
    """The state of one lesson for one student (see the module docstring)."""
    if completed:
        return DONE
    if lesson_week is None or lesson_week > now_week:
        return CLOSED
    return CURRENT if lesson_week == now_week else BEHIND


def move_week(schedule, delta: int, today: Optional[date] = None) -> int:
    """Advance (+1) or go back (-1) a week right now and return the new week. A manual schedule just changes its week.
    An auto schedule moves its start date by whole weeks, so it keeps flipping on the same weekday afterwards."""
    today = today or date.today()
    target = min(MAX_WEEK, max(0, current_week(schedule, today) + delta))
    if schedule.mode == MANUAL:
        schedule.manual_week = target
        return target
    base = schedule.start_date or today
    into_cycle = (today - base).days % 7          # days since the weekday the weeks flip on (0 on the flip day itself)
    if target == 0:                                # back before week 1: it starts again on the next flip day
        schedule.start_date = today + timedelta(days=7 - into_cycle)
    else:
        schedule.start_date = today - timedelta(days=into_cycle + 7 * (target - 1))
    return target


def hold(schedule, today: Optional[date] = None) -> None:
    """Make the week "stay": switch to manual at whatever week it is now."""
    schedule.manual_week = current_week(schedule, today)
    schedule.mode = MANUAL


def resume(schedule, today: Optional[date] = None, start_date: Optional[date] = None) -> None:
    """Let the calendar move the week again. Without a date, the current week carries on and the next one starts in 7 days."""
    today = today or date.today()
    if start_date is None:
        week = max(1, schedule.manual_week or 1)
        start_date = today - timedelta(days=7 * (week - 1))
    schedule.start_date = start_date
    schedule.mode = AUTO


def auto_assign(lessons: list, per_week: int, start_week: int = 1, overwrite: bool = False) -> int:
    """Spread lessons (already in course order) over the weeks, `per_week` to a week, from `start_week`.
    Lessons that already have a week keep it unless `overwrite`; the others fill the first weeks that still have room.
    Returns how many lessons were given a week."""
    per_week = max(1, per_week)
    taken: dict[int, int] = {}
    todo = []
    for lesson in lessons:
        if lesson.week_number is None or overwrite:
            todo.append(lesson)
        else:
            taken[lesson.week_number] = taken.get(lesson.week_number, 0) + 1
    week = max(1, start_week)
    for lesson in todo:
        while taken.get(week, 0) >= per_week:
            week += 1
        lesson.week_number = min(week, MAX_WEEK)
        taken[week] = taken.get(week, 0) + 1
    return len(todo)
