"""The View button on the teacher's Student Scores table: one student's quiz attempts, newest first."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import create_access_token, hash_password
from database import get_db
from models import Lesson, QuizAttempt, School, Subject, User
from routes import teacher_routes


def _user(db, username, role, school, **extra):
    u = User(username=username, password_hash=hash_password("Password-123"), role=role, status="active",
             school_id=school.id, created_at=date.today(), **extra)
    db.add(u)
    return u


def _token(username):
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


@pytest.fixture
def api(db, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))
    app = FastAPI()
    app.include_router(teacher_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    teacher = _user(db, "tea1", "teacher", a)
    ana = _user(db, "ana", "user", a, first_name="Ana", last_name="Cruz")
    far = _user(db, "far", "user", b)
    algebra, stats, other = Subject(name="Algebra", school_id=a.id), Subject(name="Statistics", school_id=a.id), Subject(name="Theirs", school_id=b.id)
    personal = Subject(name="Ana private", owner_user_id=None, school_id=a.id)
    db.add_all([algebra, stats, other, personal])
    db.flush()
    personal.owner_user_id = ana.id   # a personal subject of the student: never shown to the teacher
    l1 = Lesson(subject_id=algebra.id, title="Linear equations", content="x", created_by="tea1")
    l2 = Lesson(subject_id=stats.id, title="Sampling", content="x", created_by="tea1")
    l3 = Lesson(subject_id=other.id, title="Other school lesson", content="x", created_by="z")
    l4 = Lesson(subject_id=personal.id, title="Private notes", content="x", created_by="ana")
    db.add_all([l1, l2, l3, l4])
    db.flush()
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    db.add_all([
        QuizAttempt(user_id=ana.id, lesson_id=l1.id, score=3, total=10, passed=False, seconds=95, created_at=t0),
        QuizAttempt(user_id=ana.id, lesson_id=l1.id, score=9, total=10, passed=True, seconds=80, created_at=t0 + timedelta(hours=1)),
        QuizAttempt(user_id=ana.id, lesson_id=l2.id, score=5, total=10, passed=False, seconds=None, created_at=t0 + timedelta(hours=2)),
        QuizAttempt(user_id=ana.id, lesson_id=l4.id, score=10, total=10, passed=True, seconds=10, created_at=t0 + timedelta(hours=3)),
        QuizAttempt(user_id=far.id, lesson_id=l3.id, score=10, total=10, passed=True, seconds=10, created_at=t0),
    ])
    db.commit()
    return TestClient(app), {"algebra": algebra.id, "stats": stats.id, "other": other.id}


def test_lists_a_students_attempts_newest_first_with_attempt_numbers(api):
    client, ids = api
    res = client.get("/teacher/students/ana/attempts", headers=_token("tea1"))
    assert res.status_code == 200
    data = res.json()
    assert data["student"] == {"username": "ana", "name": "Ana Cruz"}
    assert [(r["lesson"], r["attempt_no"], r["score"], r["percent"], r["passed"]) for r in data["attempts"]] == [
        ("Sampling", 1, 5, 50, False),
        ("Linear equations", 2, 9, 90, True),
        ("Linear equations", 1, 3, 30, False),
    ]
    assert data["attempts"][0]["seconds"] is None
    assert data["attempts"][1]["branch"] == "Algebra"
    assert data["attempts"][2]["at"] == "2026-11-01T08:00:00Z"
    assert data["summary"] == {"attempts": 3, "passed": 1, "average_percent": 57, "seconds": 175}


def test_a_students_personal_subjects_stay_private(api):
    client, _ = api
    lessons = [r["lesson"] for r in client.get("/teacher/students/ana/attempts", headers=_token("tea1")).json()["attempts"]]
    assert "Private notes" not in lessons


def test_can_be_narrowed_to_one_branch(api):
    client, ids = api
    data = client.get(f"/teacher/students/ana/attempts?subject_id={ids['algebra']}", headers=_token("tea1")).json()
    assert {r["branch"] for r in data["attempts"]} == {"Algebra"}
    assert data["summary"]["attempts"] == 2


def test_another_schools_branch_or_student_is_not_found(api):
    client, ids = api
    assert client.get(f"/teacher/students/ana/attempts?subject_id={ids['other']}", headers=_token("tea1")).status_code == 404
    assert client.get("/teacher/students/far/attempts", headers=_token("tea1")).status_code == 404
    assert client.get("/teacher/students/nobody/attempts", headers=_token("tea1")).status_code == 404
    assert client.get("/teacher/students/tea1/attempts", headers=_token("tea1")).status_code == 404   # only students


def test_students_cannot_read_anyones_attempts(api):
    client, _ = api
    assert client.get("/teacher/students/ana/attempts", headers=_token("ana")).status_code == 403


def test_a_student_with_no_attempts_gets_an_empty_list(api, db):
    client, _ = api
    a = db.query(School).filter(School.name == "School A").first()
    _user(db, "newbie", "user", a)
    db.commit()
    data = client.get("/teacher/students/newbie/attempts", headers=_token("tea1")).json()
    assert data["attempts"] == []
    assert data["summary"] == {"attempts": 0, "passed": 0, "average_percent": 0, "seconds": 0}
