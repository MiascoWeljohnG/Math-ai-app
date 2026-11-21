"""Weekly pacing: the school admin puts lessons in weeks and decides how the current week moves; students see each lesson as
done (green), this week's (blue), behind (red) or not opened yet (gray, and they cannot open it)."""
from datetime import date, timedelta
from types import SimpleNamespace as NS

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
import weekly
from models import AuditLog, Lesson, LessonCompletion, LessonQuiz, QuizAttempt, School, Subject, User, WeeklySchedule

TODAY = date(2026, 11, 19)   # a Thursday


# ---------------------------------------------------------------- the rules (weekly.py)
def test_pace_of_a_lesson():
    assert weekly.pace(3, 3, completed=True) == "done"
    assert weekly.pace(1, 3, completed=True) == "done"          # finished late is still green
    assert weekly.pace(3, 3, completed=False) == "current"
    assert weekly.pace(2, 3, completed=False) == "behind"
    assert weekly.pace(4, 3, completed=False) == "closed"       # its week has not started
    assert weekly.pace(None, 3, completed=False) == "closed"    # never put in the plan
    assert weekly.pace(1, 0, completed=False) == "closed"       # nothing is open before the schedule starts


def test_auto_week_follows_the_calendar_and_manual_week_stays():
    auto = NS(mode="auto", start_date=TODAY - timedelta(days=15), manual_week=1)
    assert weekly.current_week(auto, TODAY) == 3                # days 0-6 week 1, 7-13 week 2, 14-20 week 3
    assert weekly.current_week(auto, TODAY + timedelta(days=6)) == 4
    assert weekly.current_week(NS(mode="auto", start_date=TODAY + timedelta(days=1), manual_week=1), TODAY) == 0
    assert weekly.current_week(NS(mode="manual", start_date=None, manual_week=2), TODAY + timedelta(days=90)) == 2


def test_moving_an_auto_schedule_keeps_the_weekday_the_weeks_flip_on():
    schedule = NS(mode="auto", start_date=date(2026, 11, 16), manual_week=1)   # a Monday
    assert weekly.move_week(schedule, 1, TODAY) == 2
    assert schedule.start_date.weekday() == 0 and weekly.current_week(schedule, TODAY) == 2
    assert weekly.move_week(schedule, -1, TODAY) == 1
    assert weekly.move_week(schedule, -1, TODAY) == 0 and weekly.current_week(schedule, TODAY) == 0
    assert schedule.start_date.weekday() == 0 and schedule.start_date > TODAY
    assert weekly.move_week(schedule, 1, TODAY) == 1


def test_hold_then_resume_keeps_the_week():
    schedule = NS(mode="auto", start_date=TODAY - timedelta(days=8), manual_week=1)   # week 2
    weekly.hold(schedule, TODAY)
    assert (schedule.mode, schedule.manual_week) == ("manual", 2)
    weekly.resume(schedule, TODAY + timedelta(days=30))
    assert schedule.mode == "auto" and weekly.current_week(schedule, TODAY + timedelta(days=30)) == 2


def test_auto_assign_fills_weeks_in_course_order():
    lessons = [NS(week_number=None) for _ in range(5)]
    assert weekly.auto_assign(lessons, per_week=2) == 5
    assert [l.week_number for l in lessons] == [1, 1, 2, 2, 3]
    lessons = [NS(week_number=1), NS(week_number=None), NS(week_number=None), NS(week_number=5)]
    weekly.auto_assign(lessons, per_week=1)                     # keeps existing weeks, fills the first free ones
    assert [l.week_number for l in lessons] == [1, 2, 3, 5]
    weekly.auto_assign(lessons, per_week=2, start_week=3, overwrite=True)
    assert [l.week_number for l in lessons] == [3, 3, 4, 4]


# ---------------------------------------------------------------- the routes
@pytest.fixture
def world(rag, db, monkeypatch):
    import auth
    from database import get_db
    from routes import subjects_routes, weekly_routes

    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))   # the School table only accepts the configured names
    db.add_all([School(name="School A"), School(name="School B")])
    db.commit()
    a, b = db.query(School).order_by(School.id).all()
    admin = User(username="admin_a", password_hash="x", role="school_admin", school_id=a.id)
    teacher = User(username="teach", password_hash="x", role="teacher", school_id=a.id)
    student = User(username="stud", password_hash="x", role="user", school_id=a.id, status="active")
    db.add_all([admin, teacher, student])
    db.commit()
    mine = Subject(name="Algebra", owner_user_id=None, school_id=a.id)
    theirs = Subject(name="Algebra", owner_user_id=None, school_id=b.id)
    db.add_all([mine, theirs])
    db.commit()

    who = {"user": student}
    app = FastAPI()
    app.include_router(subjects_routes.router)
    app.include_router(weekly_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: who["user"]
    app.dependency_overrides[auth.require_staff] = lambda: teacher
    app.dependency_overrides[auth.require_school_admin] = lambda: admin
    client = TestClient(app)
    client.db, client.subject, client.other_subject, client.student = db, mine, theirs, student
    client.as_student = lambda: who.update(user=student)
    client.as_teacher = lambda: who.update(user=teacher)
    return client


def lessons_for(world, weeks, status="published"):
    rows = []
    for i, week in enumerate(weeks):
        lesson = Lesson(subject_id=world.subject.id, title=f"Lesson {i + 1}", content="c", created_by="teach",
                        status=status, order_index=i, week_number=week)
        world.db.add(lesson)
        world.db.commit()
        rows.append(lesson)
    return rows


def schedule(world, **fields):
    row = WeeklySchedule(subject_id=world.subject.id, school_id=world.subject.school_id, **{"mode": "auto", "start_date": TODAY, **fields})
    world.db.add(row)
    world.db.commit()
    return row


def student_view(world):
    rows = world.get(f"/subjects/{world.subject.id}/lessons").json()
    return [(r["title"], r["pace"], r["locked"]) for r in rows]


def test_student_sees_blue_red_green_and_gray(world):
    one, two, three, four = lessons_for(world, [1, 2, 3, None])
    schedule(world, start_date=date.today() - timedelta(days=14))          # the school is on week 3
    world.db.add(LessonCompletion(user_id=world.student.id, lesson_id=one.id))
    world.db.commit()
    assert student_view(world) == [
        ("Lesson 1", "done", False),      # green: passed
        ("Lesson 2", "behind", False),    # red: week 2 is over and it is not finished
        ("Lesson 3", "current", False),   # blue: this week's task
        ("Lesson 4", "closed", True),     # gray: the school has not put it in the plan
    ]


def test_a_week_that_has_not_started_is_gray_and_cannot_be_opened(world):
    one, two = lessons_for(world, [1, 2])
    schedule(world, start_date=date.today())                                # week 1 only
    base = f"/subjects/{world.subject.id}/lessons"
    assert student_view(world) == [("Lesson 1", "current", False), ("Lesson 2", "closed", True)]
    assert world.get(f"{base}/{one.id}").status_code == 200
    closed = world.get(f"{base}/{two.id}")
    assert closed.status_code == 403 and "hasn't opened" in closed.json()["detail"]
    assert world.get(f"{base}/{two.id}/quiz").status_code == 403           # nor can its quiz be reached by guessing the id
    assert world.post(f"{base}/{two.id}/quiz/submit", json={"answers": {}}).status_code == 403


def test_weekly_pacing_replaces_finish_the_one_before(world):
    one, two = lessons_for(world, [1, 1])                                   # both this week: either can be done first
    schedule(world, start_date=date.today())
    assert student_view(world) == [("Lesson 1", "current", False), ("Lesson 2", "current", False)]
    assert world.get(f"/subjects/{world.subject.id}/lessons/{two.id}").status_code == 200


def test_pacing_switched_off_goes_back_to_one_lesson_at_a_time(world):
    lessons_for(world, [1, 1])
    schedule(world, start_date=date.today(), enabled=False)
    assert student_view(world) == [("Lesson 1", None, False), ("Lesson 2", None, True)]


def test_teachers_are_never_held_back_by_the_schedule(world):
    _, two = lessons_for(world, [1, None])
    schedule(world, start_date=date.today())
    world.as_teacher()
    rows = world.get(f"/subjects/{world.subject.id}/lessons").json()
    assert all(not r["locked"] and r["pace"] is None for r in rows)
    assert world.get(f"/subjects/{world.subject.id}/lessons/{two.id}").status_code == 200


def test_admin_sets_a_lessons_week_and_takes_it_out_again(world):
    one, = lessons_for(world, [None])
    url = f"/school-admin/weekly/{world.subject.id}/lessons/{one.id}"
    assert world.put(url, json={"week_number": 4}).json()["lessons"][0]["week_number"] == 4
    assert world.put(url, json={"week_number": None}).json()["lessons"][0]["week_number"] is None
    assert world.put(url, json={"week_number": 0}).status_code == 422
    assert world.db.query(AuditLog).filter(AuditLog.action == "weekly.lesson").count() == 2


def test_a_draft_cannot_be_put_in_the_plan(world):
    draft, = lessons_for(world, [None], status="draft")
    assert world.put(f"/school-admin/weekly/{world.subject.id}/lessons/{draft.id}", json={"week_number": 1}).status_code == 409


def test_admin_auto_assigns_lessons(world):
    lessons_for(world, [None] * 5)
    state = world.post(f"/school-admin/weekly/{world.subject.id}/auto-assign", json={"per_week": 2}).json()
    assert [l["week_number"] for l in state["lessons"]] == [1, 1, 2, 2, 3]


def test_admin_turns_pacing_on_holds_the_week_and_advances_it(world):
    lessons_for(world, [1, 2, 3])
    base = f"/school-admin/weekly/{world.subject.id}"
    assert world.get(base).json()["schedule"] is None                       # not on yet: students see the old behaviour
    on = world.put(f"{base}/schedule", json={"mode": "auto", "start_date": date.today().isoformat()}).json()
    assert on["schedule"]["mode"] == "auto" and on["schedule"]["current_week"] == 1
    held = world.put(f"{base}/schedule", json={"mode": "manual"}).json()    # "stay": the week stops moving
    assert held["schedule"]["mode"] == "manual" and held["schedule"]["current_week"] == 1
    assert world.post(f"{base}/week", json={"action": "next"}).json()["schedule"]["current_week"] == 2
    assert student_view(world) == [("Lesson 1", "behind", False), ("Lesson 2", "current", False), ("Lesson 3", "closed", True)]
    assert world.post(f"{base}/week", json={"action": "previous"}).json()["schedule"]["current_week"] == 1
    back = world.put(f"{base}/schedule", json={"mode": "auto"}).json()      # let the calendar move it again
    assert back["schedule"]["mode"] == "auto" and back["schedule"]["current_week"] == 1


def test_admin_sees_how_many_students_are_behind(world):
    one, two = lessons_for(world, [1, 2])
    schedule(world, start_date=date.today() - timedelta(days=7))            # week 2: lesson 1 is overdue
    rows = world.get(f"/school-admin/weekly/{world.subject.id}").json()["lessons"]
    assert (rows[0]["behind"], rows[0]["completed"]) == (1, 0) and rows[1]["behind"] == 0
    world.db.add(LessonCompletion(user_id=world.student.id, lesson_id=one.id))
    world.db.commit()
    assert world.get(f"/school-admin/weekly/{world.subject.id}").json()["lessons"][0]["behind"] == 0


def test_moving_the_week_needs_pacing_to_be_on_first(world):
    assert world.post(f"/school-admin/weekly/{world.subject.id}/week", json={"action": "next"}).status_code == 409


def test_another_schools_subject_cannot_be_touched(world):
    other = f"/school-admin/weekly/{world.other_subject.id}"
    assert world.get(other).status_code == 404
    assert world.put(f"{other}/schedule", json={"mode": "auto"}).status_code == 404
    assert world.post(f"{other}/auto-assign", json={}).status_code == 404
    assert [s["id"] for s in world.get("/school-admin/weekly").json()] == [world.subject.id]


# ---------------------------------------------------------------- the roadmap shows the same colours
def test_roadmap_carries_the_pace_and_plans_only_open_lessons(world):
    from routes import learning_routes
    from fastapi import FastAPI
    import auth
    from database import get_db
    one, two, three, four = lessons_for(world, [None, 2, 1, 3])
    schedule(world, start_date=date.today() - timedelta(days=7))            # week 2
    app = FastAPI()
    app.include_router(learning_routes.router)
    app.dependency_overrides[get_db] = lambda: world.db
    app.dependency_overrides[auth.get_current_user] = lambda: world.student
    subject = TestClient(app).get(f"/learning/roadmap?subject_id={world.subject.id}").json()["subjects"][0]
    assert subject["weekly"] is True and subject["current_week"] == 2
    assert [(l["title"], l["pace"]) for l in subject["lessons"]] == [   # week order, unscheduled last
        ("Lesson 3", "behind"), ("Lesson 2", "current"), ("Lesson 4", "closed"), ("Lesson 1", "closed")]
    assert [item["title"] for item in subject["study_plan"]] == ["Lesson 3", "Lesson 2"]   # nothing gray in the plan


# ---------------------------------------------------------------- "completed" means the same on every page
def roadmap_of(world):
    from routes import learning_routes
    import auth
    from database import get_db
    app = FastAPI()
    app.include_router(learning_routes.router)
    app.dependency_overrides[get_db] = lambda: world.db
    app.dependency_overrides[auth.get_current_user] = lambda: world.student
    return TestClient(app).get(f"/learning/roadmap?subject_id={world.subject.id}").json()["subjects"][0]


def add_quiz(world, lesson, *attempts):
    world.db.add(LessonQuiz(lesson_id=lesson.id, questions="[]", difficulty=3))
    for score, passed in attempts:
        world.db.add(QuizAttempt(user_id=world.student.id, lesson_id=lesson.id, score=score, total=10, passed=passed))
    world.db.commit()


def test_a_completion_record_without_a_passed_quiz_does_not_count(world):
    """The reported bug: the lessons page showed lesson 1 as completed while the roadmap said 0 of 6 done."""
    one, two = lessons_for(world, [None, None])
    world.db.add(LessonCompletion(user_id=world.student.id, lesson_id=one.id))   # a leftover from when a click completed a lesson
    add_quiz(world, one, (2, False))                                             # ...but the quiz was never passed
    world.db.commit()
    lessons = world.get(f"/subjects/{world.subject.id}/lessons").json()
    assert [(l["title"], l["completed"], l["locked"]) for l in lessons] == [("Lesson 1", False, False), ("Lesson 2", False, True)]
    roadmap = roadmap_of(world)
    assert roadmap["completed"] == 0 and [l["status"] for l in roadmap["lessons"]][0] != "done"


def test_passing_the_quiz_completes_the_lesson_everywhere(world):
    one, two = lessons_for(world, [None, None])
    add_quiz(world, one, (2, False), (9, True))
    world.db.add(LessonCompletion(user_id=world.student.id, lesson_id=one.id))   # what a real pass records
    world.db.commit()
    lessons = world.get(f"/subjects/{world.subject.id}/lessons").json()
    assert (lessons[0]["completed"], lessons[1]["locked"]) == (True, False)       # lesson 2 opened up
    assert roadmap_of(world)["completed"] == 1


def test_a_lesson_with_no_quiz_still_counts_when_marked_complete(world):
    one, two = lessons_for(world, [None, None])
    world.db.add(LessonCompletion(user_id=world.student.id, lesson_id=one.id))
    world.db.commit()
    assert world.get(f"/subjects/{world.subject.id}/lessons").json()[0]["completed"] is True
    assert roadmap_of(world)["completed"] == 1


def test_weekly_green_needs_a_passed_quiz_too(world):
    one, two = lessons_for(world, [1, 1])
    schedule(world, start_date=date.today())
    world.db.add(LessonCompletion(user_id=world.student.id, lesson_id=one.id))
    add_quiz(world, one, (3, False))
    assert student_view(world)[0] == ("Lesson 1", "current", False)               # blue, not green
    assert world.get(f"/school-admin/weekly/{world.subject.id}").json()["lessons"][0]["completed"] == 0


def test_a_students_own_subject_counts_a_click(world):
    from progress import progress_for_user
    mine = Subject(name="My notes", owner_user_id=world.student.id)
    world.db.add(mine)
    world.db.commit()
    lesson = Lesson(subject_id=mine.id, title="Mine", content="c", created_by="stud", status="published", order_index=0)
    world.db.add(lesson)
    world.db.commit()
    world.db.add(LessonCompletion(user_id=world.student.id, lesson_id=lesson.id))
    add_quiz(world, lesson)                                                        # has a quiz, never taken: a click still counts here
    row = next(r for r in progress_for_user(world.db, world.student) if r["subject_id"] == mine.id)
    assert row["completed"] == 1


def test_home_progress_agrees_with_the_lessons_page(world):
    from progress import progress_for_user
    one, two = lessons_for(world, [None, None])
    world.db.add(LessonCompletion(user_id=world.student.id, lesson_id=one.id))
    add_quiz(world, one, (2, False))
    row = next(r for r in progress_for_user(world.db, world.student) if r["subject_id"] == world.subject.id)
    assert (row["completed"], row["total"]) == (0, 2)
