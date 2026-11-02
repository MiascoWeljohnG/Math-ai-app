from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import create_access_token, hash_password
from database import get_db
from models import ACTIVE, DISABLED, PENDING, Material, School, Subject, SubjectDeletionRequest, User
from routes import school_admin_routes


def _user(db, username, role, school, status=ACTIVE, last_seen=None, created=None):
    u = User(username=username, password_hash=hash_password("Password-123"), role=role, status=status,
             school_id=school.id, last_seen_at=last_seen, created_at=created or date.today())
    db.add(u)
    return u


@pytest.fixture
def api(db, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))
    app = FastAPI()
    app.include_router(school_admin_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    admin = _user(db, "admin_a", "school_admin", a)
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': admin.username})}"}
    return TestClient(app), db, a, b, admin, headers


def test_overview_counts_only_the_admins_own_school(api):
    client, db, a, b, admin, headers = api
    now = datetime.utcnow()
    _user(db, "stu1", "user", a, last_seen=now - timedelta(minutes=2))        # online now
    _user(db, "stu2", "user", a, last_seen=now - timedelta(hours=3))          # seen today, not online
    _user(db, "stu3", "user", a, last_seen=None)                              # never seen
    _user(db, "tea1", "teacher", a, last_seen=now - timedelta(minutes=10))    # online now
    _user(db, "stu_pending", "user", a, status=PENDING, created=date.today() - timedelta(days=4))
    _user(db, "retired", "admin", a, status=DISABLED)
    _user(db, "other_stu", "user", b, last_seen=now)                          # another school: never counted
    _user(db, "other_pending", "user", b, status=PENDING)
    db.add_all([
        Material(filename="a1", display_name="A1", branch="Algebra", uploaded_by="tea1", school_id=a.id, uploaded_at=now - timedelta(days=1)),
        Material(filename="a2", display_name="A2", branch="Algebra", uploaded_by="tea1", school_id=a.id, uploaded_at=now - timedelta(days=30)),
        Material(filename="b1", display_name="B1", branch="Algebra", uploaded_by="x", school_id=b.id, uploaded_at=now),
    ])
    mine = Subject(name="Mine", school_id=a.id)
    theirs = Subject(name="Theirs", school_id=b.id)
    db.add_all([mine, theirs])
    db.flush()
    db.add_all([
        SubjectDeletionRequest(subject_id=mine.id, subject_name="Mine", requested_by="tea1", status="pending"),
        SubjectDeletionRequest(subject_id=mine.id, subject_name="Mine", requested_by="tea1", status="approved"),   # settled: not counted
        SubjectDeletionRequest(subject_id=theirs.id, subject_name="Theirs", requested_by="x", status="pending"),   # other school
    ])
    db.commit()

    data = client.get("/school-admin/overview", headers=headers).json()

    # active: admin_a + stu1..3 + tea1 = 5 (pending and retired are not active); total excludes only the retired one
    assert data["accounts"] == {"active": 5, "total": 6, "students": 3, "teachers": 1, "admins": 1}
    assert data["files"]["total"] == 2 and data["files"]["this_week"] == 1 and data["files"]["latest"].endswith("Z")
    # online now: stu1, tea1, and the admin themself (this very request stamps them)
    assert data["online"]["now"] == 3 and data["online"]["students"] == 1 and data["online"]["teachers"] == 1
    assert data["online"]["today"] == 4   # + stu2
    assert data["attention"] == {"approvals": 1, "deletions": 1, "oldest_approval_days": 4}


def test_overview_of_an_empty_school_is_all_zeroes(api):
    client, db, a, b, admin, headers = api
    data = client.get("/school-admin/overview", headers=headers).json()
    assert data["files"] == {"total": 0, "this_week": 0, "latest": None}
    assert data["attention"] == {"approvals": 0, "deletions": 0, "oldest_approval_days": None}
    assert data["accounts"]["active"] == 1


def test_any_authenticated_request_stamps_last_seen_once_a_minute(api):
    client, db, a, b, admin, headers = api
    assert admin.last_seen_at is None
    client.get("/school-admin/users", headers=headers)
    first = db.get(User, admin.id).last_seen_at
    assert first is not None
    client.get("/school-admin/users", headers=headers)          # inside the throttle window: not rewritten
    assert db.get(User, admin.id).last_seen_at == first


def test_only_school_admins_can_read_the_overview(api):
    client, db, a, b, admin, headers = api
    teacher = _user(db, "tea_x", "teacher", a)
    db.commit()
    token = create_access_token({"sub": teacher.username})
    assert client.get("/school-admin/overview", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.get("/school-admin/overview").status_code == 401
