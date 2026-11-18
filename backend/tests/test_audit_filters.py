"""The school admin's audit log can be narrowed by time, by who did it, and by what happened."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import create_access_token, hash_password
from database import get_db
from models import ACTIVE, AuditLog, School, User
from routes import school_admin_routes


def _headers(username):
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


@pytest.fixture
def api(db, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))
    app = FastAPI()
    app.include_router(school_admin_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    for name, role, school in [("admin_a", "school_admin", a), ("tea1", "teacher", a), ("stu1", "user", a), ("stu_b", "user", b)]:
        db.add(User(username=name, password_hash=hash_password("Password-123"), role=role, status=ACTIVE, school_id=school.id))
    now = datetime.utcnow()
    for actor, action, age, school in [
        ("stu1", "student.register", timedelta(hours=0), a),          # just now
        ("admin_a", "student.approve", timedelta(days=1), a),         # about a day ago
        ("tea1", "subject.delete.request", timedelta(days=5), a),
        ("tea1", "file.delete.request", timedelta(days=20), a),
        ("admin_a", "users.view", timedelta(days=200), a),
        ("stu_b", "student.register", timedelta(hours=0), b),         # another school
    ]:
        db.add(AuditLog(actor=actor, school_id=school.id, action=action, target="x", created_at=now - age))
    db.commit()
    return TestClient(app)


def _get(client, **params):
    response = client.get("/school-admin/audit-log", params=params, headers=_headers("admin_a"))
    assert response.status_code == 200
    return [(r["actor"], r["action"]) for r in response.json()]


def test_who_filter_separates_students_teachers_and_admins(api):
    assert _get(api, role="user") == [("stu1", "student.register")]
    assert {a for a, _ in _get(api, role="teacher")} == {"tea1"}
    assert {a for a, _ in _get(api, role="school_admin")} == {"admin_a"}
    assert api.get("/school-admin/audit-log", params={"role": "nope"}, headers=_headers("admin_a")).status_code == 400


def test_when_filter_uses_since_and_until(api):
    now = datetime.utcnow()
    week = _get(api, since=(now - timedelta(days=7)).isoformat() + "Z")
    assert len(week) == 3
    month = _get(api, since=(now - timedelta(days=30)).isoformat() + "Z")
    assert len(month) == 4
    yesterday = _get(api, since=(now - timedelta(days=2)).isoformat() + "Z", until=(now - timedelta(hours=12)).isoformat() + "Z")
    assert yesterday == [("admin_a", "student.approve")]


def test_what_filter_takes_exact_codes_and_wildcards(api):
    assert _get(api, actions="student.register") == [("stu1", "student.register")]
    assert {b for _, b in _get(api, actions="*.delete.request")} == {"subject.delete.request", "file.delete.request"}
    assert {b for _, b in _get(api, actions="*.view")} == {"users.view"}


def test_filters_combine_and_stay_inside_the_school(api):
    assert _get(api, role="teacher", actions="file.delete.request") == [("tea1", "file.delete.request")]
    assert _get(api, role="user", actions="student.approve") == []
    assert ("stu_b", "student.register") not in _get(api)
