"""Quiz attempts, failed-quiz breakdown, leaderboard, roadmap/study plan and reminders. The model is faked (see conftest.py)."""
import json
import types
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from database import get_db
from models import Lesson, LessonCompletion, LessonQuiz, QuizAttempt, Subject, User, School
from routes import learning_routes, subjects_routes

QUESTIONS = [
    {"type": "mcq", "question": "2+2?", "choices": ["3", "4"], "answer": 1, "explanation": "Add."},
    {"type": "tf", "question": "1 is even.", "answer": False, "explanation": "Odd."},
    {"type": "num", "question": "3*3?", "answer": "9", "explanation": "Multiply."},
    {"type": "mcq", "question": "5-1?", "choices": ["4", "6"], "answer": 0, "explanation": "Subtract."},
    {"type": "tf", "question": "0 is even.", "answer": True, "explanation": "Even."},
]
ALL_RIGHT = {"0": 1, "1": False, "2": "9", "3": 0, "4": True}
ALL_WRONG = {"0": 0, "1": True, "2": "1", "3": 1, "4": False}


@pytest.fixture
def api(db, rag):
    users = {n: User(username=n, password_hash="x", role=r, status="active") for n, r in
             [("ann", "user"), ("bob", "user"), ("teach", "teacher"), ("teach2", "teacher"), ("boss", "school_admin")]}
    school = School(name="School A")   # the school admin needs a school; the other accounts stay in the old no-school pool
    db.add(school)
    db.flush()
    users["boss"].school_id = school.id
    db.add_all(users.values())
    algebra = Subject(name="Algebra")
    db.add(algebra)
    db.commit()
    lessons = [Lesson(subject_id=algebra.id, title=f"L{n}", content="word " * 400, order_index=n, created_by="teach") for n in (1, 2, 3, 4)]
    db.add_all(lessons)
    db.commit()
    db.add(LessonQuiz(lesson_id=lessons[0].id, questions=json.dumps(QUESTIONS), difficulty=2))
    db.commit()

    app, current = FastAPI(), {"user": users["ann"]}
    app.include_router(subjects_routes.router)
    app.include_router(learning_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    quiz = f"/subjects/{algebra.id}/lessons/{lessons[0].id}/quiz"

    def login(name):
        current["user"] = users[name]

    return types.SimpleNamespace(client=TestClient(app), login=login, db=db, rag=rag, quiz=quiz,
                                 lessons=lessons, users=users, subject=algebra)


# ---------------------------------------------------------------- attempts
def test_submit_saves_the_attempt_with_time_and_missed_questions(api):
    r = api.client.post(api.quiz + "/submit", json={"answers": {**ALL_RIGHT, "2": "1"}, "seconds": 70}).json()
    assert (r["score"], r["recorded"]) == (4, True)
    attempt = api.db.query(QuizAttempt).one()
    assert (attempt.score, attempt.total, attempt.seconds, attempt.passed) == (4, 5, 70, True)
    assert json.loads(attempt.missed) == [2]


def test_reported_time_is_capped_near_the_quiz_limit(api):
    api.client.post(api.quiz + "/submit", json={"answers": ALL_RIGHT, "seconds": 80_000})
    limit = 5 * subjects_routes.SECONDS_PER_QUESTION[2]
    assert api.db.query(QuizAttempt).one().seconds == limit + 30


def test_teacher_preview_is_not_recorded(api):
    api.login("teach")
    assert api.client.post(api.quiz + "/submit", json={"answers": ALL_RIGHT}).json()["recorded"] is False
    assert api.db.query(QuizAttempt).count() == 0


# ---------------------------------------------------------------- breakdown
def test_failed_quiz_gets_an_ai_breakdown_that_is_saved(api):
    api.client.post(api.quiz + "/submit", json={"answers": ALL_WRONG})
    api.rag.reply = ["1. Add 2 and 2 to get 4.", "SHOULD NOT BE USED"]
    first = api.client.post(api.quiz + "/breakdown").json()
    assert first["breakdown"].startswith("1. Add")
    assert api.client.post(api.quiz + "/breakdown").json() == first   # cached: the 2nd reply was never asked for
    assert api.rag.reply == ["SHOULD NOT BE USED"]


def test_breakdown_needs_a_failed_attempt(api):
    assert api.client.post(api.quiz + "/breakdown").status_code == 404
    api.client.post(api.quiz + "/submit", json={"answers": ALL_RIGHT})
    assert api.client.post(api.quiz + "/breakdown").status_code == 400


def test_breakdown_model_failure_is_a_502_and_can_be_retried(api):
    api.client.post(api.quiz + "/submit", json={"answers": ALL_WRONG})
    api.rag.reply = [RuntimeError("down"), "Step 1."]
    assert api.client.post(api.quiz + "/breakdown").status_code == 502
    assert api.client.post(api.quiz + "/breakdown").json()["breakdown"] == "Step 1."


# ---------------------------------------------------------------- leaderboard
def test_leaderboard_ranks_best_attempt_then_speed_and_marks_you(api):
    api.client.post(api.quiz + "/submit", json={"answers": ALL_WRONG, "seconds": 10})            # ann's worse try
    api.client.post(api.quiz + "/submit", json={"answers": ALL_RIGHT, "seconds": 90})            # ann's best: 5/5 in 90s
    api.login("bob")
    api.client.post(api.quiz + "/submit", json={"answers": ALL_RIGHT, "seconds": 60})            # same score, faster
    entries = api.client.get(api.quiz + "/leaderboard").json()["entries"]
    assert [(e["name"], e["rank"], e["seconds"], e["you"]) for e in entries] == [("bob", 1, 60, True), ("ann", 2, 90, False)]


# ---------------------------------------------------------------- roadmap
def test_roadmap_marks_done_next_and_builds_a_study_plan(api):
    api.client.post(api.quiz + "/submit", json={"answers": ALL_RIGHT})   # ann passes L1
    api.db.add(LessonCompletion(user_id=api.users["ann"].id, lesson_id=api.lessons[1].id))   # L2: read, has no quiz
    api.db.commit()
    subject = api.client.get("/learning/roadmap").json()["subjects"][0]
    assert [l["status"] for l in subject["lessons"]] == ["done", "done", "next", "upcoming"]
    assert (subject["completed"], subject["total"], subject["percent"]) == (2, 4, 50)
    assert [p["title"] for p in subject["study_plan"]] == ["L3", "L4"]
    assert subject["study_plan"][0]["steps"][0]["text"] == "Read the lesson"
    assert subject["study_plan"][0]["minutes"] == sum(s["minutes"] for s in subject["study_plan"][0]["steps"])


def test_failed_lesson_stays_next_and_plan_says_to_review(api):
    api.client.post(api.quiz + "/submit", json={"answers": ALL_WRONG})
    subject = api.client.get(f"/learning/roadmap?subject_id={api.subject.id}").json()["subjects"][0]
    first = subject["lessons"][0]
    assert (first["status"], first["attempts"], first["best_percent"]) == ("next", 1, 0)
    assert subject["study_plan"][0]["steps"][0]["text"].startswith("Re-read")


# ---------------------------------------------------------------- reminders
def test_teacher_reminders_reach_the_right_students(api):
    api.login("teach")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert api.client.post("/learning/reminders", json={"message": "Finish L1"}).status_code == 200
    assert api.client.post("/learning/reminders", json={"message": "Ann only", "student_username": "ann", "due_date": tomorrow}).status_code == 200
    api.login("ann")
    assert [r["message"] for r in api.client.get("/learning/reminders").json()] == ["Ann only", "Finish L1"]   # dated first
    api.login("bob")
    assert [r["message"] for r in api.client.get("/learning/reminders").json()] == ["Finish L1"]


def test_reminder_rules(api):
    api.login("ann")
    assert api.client.post("/learning/reminders", json={"message": "hi"}).status_code == 403          # students can't write
    api.login("teach")
    assert api.client.post("/learning/reminders", json={"message": "hi", "student_username": "nobody"}).status_code == 404
    assert api.client.post("/learning/reminders", json={"message": "hi", "student_username": "teach2"}).status_code == 404   # not a student
    assert api.client.post("/learning/reminders", json={"message": "   "}).status_code == 400
    rid = api.client.post("/learning/reminders", json={"message": "mine"}).json()["id"]
    api.login("teach2")
    assert api.client.get("/learning/reminders").json() == []                                         # sees only their own
    assert api.client.delete(f"/learning/reminders/{rid}").status_code == 403
    api.login("boss")
    assert api.client.delete(f"/learning/reminders/{rid}").status_code == 200                          # the school admin may delete any


def test_notification_model_exists_and_routes_import():
    import models
    from routes import notification_routes  # noqa: F401  (these crashed the app at startup)
    assert models.Notification.__tablename__ == "notifications"


# ---------------------------------------------------------------- rankings
def _attempt(api, name, lesson, score, seconds, passed=None, total=10):
    api.db.add(QuizAttempt(user_id=api.users[name].id, lesson_id=lesson.id, score=score, total=total, seconds=seconds,
                           passed=score * 10 >= 8 * total if passed is None else passed))
    api.db.commit()


@pytest.fixture
def ranked(api):
    geometry = Subject(name="Geometry")
    api.db.add(geometry)
    api.db.commit()
    g1 = Lesson(subject_id=geometry.id, title="G1", content="x", order_index=1, created_by="teach")
    api.db.add(g1)
    api.db.commit()
    a1, a2 = api.lessons[0], api.lessons[1]
    _attempt(api, "ann", a1, 6, 50)     # ann's first try fails...
    _attempt(api, "ann", a1, 9, 90)     # ...then passes with 90%
    _attempt(api, "ann", a2, 8, 100)    # passes lesson 2 with 80%
    _attempt(api, "bob", a1, 10, 60)    # bob: one perfect lesson
    _attempt(api, "bob", g1, 10, 30)    # and a perfect Geometry lesson
    api.geometry = geometry
    return api


def test_rankings_order_by_lessons_passed_then_average_then_time(ranked):
    data = ranked.client.get("/learning/rankings").json()
    assert [(r["rank"], r["name"], r["lessons_passed"], r["average_percent"], r["seconds"]) for r in data["entries"]] == [
        (1, "bob", 2, 100, 90), (2, "ann", 2, 85, 190)]
    assert [b["name"] for b in data["branches"]] == ["Algebra", "Geometry"]
    assert [r["you"] for r in data["entries"]] == [False, True]          # the caller is ann


def test_rankings_filter_by_branch(ranked):
    algebra = ranked.client.get(f"/learning/rankings?subject_id={ranked.subject.id}").json()["entries"]
    assert [(r["name"], r["lessons_passed"]) for r in algebra] == [("ann", 2), ("bob", 1)]   # Geometry's pass doesn't count here
    geometry = ranked.client.get(f"/learning/rankings?subject_id={ranked.geometry.id}").json()["entries"]
    assert [r["name"] for r in geometry] == ["bob"]
    assert ranked.client.get("/learning/rankings?subject_id=9999").status_code == 404


def test_personal_subjects_never_appear_in_rankings(ranked):
    personal = Subject(name="Mine", owner_user_id=ranked.users["ann"].id)
    ranked.db.add(personal)
    ranked.db.commit()
    lesson = Lesson(subject_id=personal.id, title="P1", content="x", order_index=1, created_by="ann")
    ranked.db.add(lesson)
    ranked.db.commit()
    _attempt(ranked, "ann", lesson, 10, 10)
    assert ranked.client.get(f"/learning/rankings?subject_id={personal.id}").status_code == 404
    entries = ranked.client.get("/learning/rankings").json()["entries"]
    assert next(r for r in entries if r["name"] == "ann")["lessons_passed"] == 2   # the personal pass is not counted


def test_student_outside_the_top_still_sees_their_own_rank(ranked):
    data = ranked.client.get("/learning/rankings?limit=1").json()
    assert [r["name"] for r in data["entries"]] == ["bob"]
    assert (data["me"]["rank"], data["me"]["name"]) == (2, "ann")
    assert ranked.client.get("/learning/rankings?limit=5").json()["me"] is None


def test_teachers_see_usernames_and_attempts_but_students_do_not(ranked):
    student_row = ranked.client.get("/learning/rankings").json()["entries"][0]
    assert "username" not in student_row and "attempts" not in student_row
    ranked.login("teach")
    rows = {r["name"]: r for r in ranked.client.get("/learning/rankings?limit=200").json()["entries"]}
    assert (rows["ann"]["username"], rows["ann"]["attempts"], rows["bob"]["attempts"]) == ("ann", 3, 2)
    assert not any(r["you"] for r in rows.values())                     # a teacher is not a ranked student
