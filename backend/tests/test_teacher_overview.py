from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import create_access_token, hash_password
from database import get_db
from models import ACTIVE, PENDING, Lesson, Material, School, Subject, User
from routes import teacher_routes


def _user(db, username, role, school, status=ACTIVE, last_seen=None):
    u = User(username=username, password_hash=hash_password("Password-123"), role=role, status=status,
             school_id=school.id, last_seen_at=last_seen, created_at=date.today())
    db.add(u)
    return u


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
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': teacher.username})}"}
    return TestClient(app), db, a, b, headers


def test_teacher_overview_counts_own_files_and_school_lessons_and_students(api):
    client, db, a, b, headers = api
    now = datetime.utcnow()
    db.add_all([
        Material(filename="m1", display_name="One.pdf", branch="Algebra", uploaded_by="tea1", school_id=a.id, uploaded_at=now - timedelta(days=1)),
        Material(filename="m2", display_name="Two.PDF", branch="Algebra", uploaded_by="tea1", school_id=a.id, uploaded_at=now - timedelta(days=30)),
        Material(filename="m3", display_name="Three.docx", branch="Algebra", uploaded_by="tea1", school_id=a.id, uploaded_at=now),
        Material(filename="m4", display_name="Four.pptx", branch="Algebra", uploaded_by="tea1", school_id=a.id, uploaded_at=now),
        Material(filename="m5", display_name="Other teacher.pdf", branch="Algebra", uploaded_by="someone_else", school_id=a.id, uploaded_at=now),
    ])
    mine, theirs = Subject(name="Mine", school_id=a.id), Subject(name="Theirs", school_id=b.id)
    db.add_all([mine, theirs])
    db.flush()
    db.add_all([
        Lesson(subject_id=mine.id, title="d1", content="x", created_by="tea1", status="draft", created_at=now - timedelta(days=3)),
        Lesson(subject_id=mine.id, title="d2", content="x", created_by="tea2", status="draft"),
        Lesson(subject_id=mine.id, title="p1", content="x", created_by="tea1", status="published"),
        Lesson(subject_id=theirs.id, title="other school draft", content="x", created_by="z", status="draft"),
    ])
    _user(db, "stu1", "user", a, last_seen=now - timedelta(minutes=2))
    _user(db, "stu2", "user", a, last_seen=now - timedelta(days=3))
    _user(db, "stu3", "user", a, last_seen=None)
    _user(db, "stu_pending", "user", a, status=PENDING)
    _user(db, "other_stu", "user", b, last_seen=now)
    db.commit()

    body = client.get("/teacher/overview", headers=headers).json()

    assert body["files"]["total"] == 4                      # the other teacher's file is not mine
    assert (body["files"]["pdf"], body["files"]["docx"], body["files"]["other"]) == (2, 1, 1)
    assert body["files"]["this_week"] == 3
    assert body["lessons"]["drafts"] == 2                   # the other school's draft is not counted
    assert body["lessons"]["my_drafts"] == 1
    assert body["lessons"]["oldest_draft_days"] == 3
    assert body["lessons"]["published"] == 1 and body["lessons"]["my_published"] == 1
    assert body["lessons"]["subjects"] == 1
    assert body["students"] == {"active": 3, "online": 1, "today": 1, "week": 2, "window_minutes": 15}


def test_teacher_overview_when_nothing_exists(api):
    client, _, _, _, headers = api
    body = client.get("/teacher/overview", headers=headers).json()
    assert body["files"]["total"] == 0 and body["files"]["latest"] is None
    assert body["lessons"]["drafts"] == 0 and body["lessons"]["oldest_draft_days"] == 0
    assert body["students"]["active"] == 0
