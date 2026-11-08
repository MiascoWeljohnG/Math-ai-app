"""Who opened the lists of people's details is part of the audit log, once per list per 30 minutes."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import audit
import config
from auth import create_access_token, hash_password
from database import get_db
from models import ACTIVE, PENDING, AuditLog, School, Subject, User
from routes import approval_routes, file_deletion_routes, learning_routes, school_admin_routes, subject_deletion_routes, teacher_routes


def _headers(username):
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


@pytest.fixture
def api(db, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))
    app = FastAPI()
    for module in (school_admin_routes, approval_routes, subject_deletion_routes, file_deletion_routes, teacher_routes, learning_routes):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: db
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    for name, role, school, status in [
        ("admin_a", "school_admin", a, ACTIVE), ("tea1", "teacher", a, ACTIVE), ("stu1", "user", a, ACTIVE),
        ("pend1", "user", a, PENDING), ("admin_b", "school_admin", b, ACTIVE),
    ]:
        db.add(User(username=name, password_hash=hash_password("Password-123"), role=role, status=status, school_id=school.id))
    db.add_all([Subject(name="Algebra", school_id=a.id), Subject(name="Geometry", school_id=a.id)])
    db.commit()
    return TestClient(app), db


def _rows(db, **filters):
    return db.query(AuditLog).filter_by(**filters).order_by(AuditLog.id).all()


def test_every_named_list_leaves_one_entry_for_the_person_who_opened_it(api):
    client, db = api
    assert client.get("/school-admin/users", headers=_headers("admin_a")).status_code == 200
    assert client.get("/approvals/pending", headers=_headers("admin_a")).status_code == 200
    assert client.get("/subject-deletions", headers=_headers("admin_a")).status_code == 200
    assert client.get("/file-deletions", headers=_headers("admin_a")).status_code == 200
    assert client.get("/teacher/students", headers=_headers("tea1")).status_code == 200
    assert client.get("/learning/rankings", headers=_headers("tea1")).status_code == 200

    seen = {(r.actor, r.action) for r in _rows(db)}
    assert seen == {
        ("admin_a", "users.view"), ("admin_a", "approvals.view"), ("admin_a", "subject.delete.view"),
        ("admin_a", "file.delete.view"), ("tea1", "roster.view"), ("tea1", "scores.view"),
    }
    assert {r.school_id for r in _rows(db)} == {db.query(School).filter_by(name="School A").one().id}   # filed under the actor's school
    assert _rows(db, action="users.view")[0].detail == "4 accounts"
    assert _rows(db, action="approvals.view")[0].detail == "1 waiting"
    assert _rows(db, action="roster.view")[0].detail == "1 students"
    assert _rows(db, action="scores.view")[0].target == "All branches"


def test_refreshing_does_not_fill_the_log_but_a_later_visit_is_recorded(api):
    client, db = api
    for _ in range(6):   # the page polls every 30 seconds
        client.get("/school-admin/users", headers=_headers("admin_a"))
    assert len(_rows(db, action="users.view")) == 1

    _rows(db, action="users.view")[0].created_at = datetime.utcnow() - audit.VIEW_WINDOW - timedelta(minutes=1)
    db.commit()
    client.get("/school-admin/users", headers=_headers("admin_a"))
    assert len(_rows(db, action="users.view")) == 2


def test_student_scores_are_logged_per_branch_and_only_for_staff(api):
    client, db = api
    branches = client.get("/learning/rankings", headers=_headers("stu1")).json()["branches"]
    assert _rows(db) == []                                                   # a student looking at the public ranking is not logged
    geometry = next(b["id"] for b in branches if b["name"] == "Geometry")
    client.get("/learning/rankings", headers=_headers("tea1"))
    client.get(f"/learning/rankings?subject_id={geometry}", headers=_headers("tea1"))
    client.get(f"/learning/rankings?subject_id={geometry}", headers=_headers("tea1"))   # same branch again: still one
    assert [r.target for r in _rows(db, action="scores.view")] == ["All branches", "Geometry"]


def test_a_teacher_opening_subject_deletion_state_is_not_logged(api):
    client, db = api
    client.get("/subject-deletions", headers=_headers("tea1"))
    assert _rows(db, action="subject.delete.view") == []


def test_the_school_admin_reads_it_in_the_log_with_a_section_filter(api):
    client, db = api
    client.get("/school-admin/users", headers=_headers("admin_a"))
    client.get("/teacher/students", headers=_headers("tea1"))
    client.get("/learning/rankings", headers=_headers("tea1"))
    client.get("/file-deletions", headers=_headers("admin_a"))

    def actions(**params):
        response = client.get("/school-admin/audit-log", params=params, headers=_headers("admin_a"))
        assert response.status_code == 200
        return {row["action"] for row in response.json()}

    assert actions() >= {"users.view", "roster.view", "scores.view", "file.delete.view"}
    assert actions(section="scores_roster") == {"roster.view", "scores.view"}
    assert actions(section="people") == {"users.view"}
    assert actions(section="file_deletions") == {"file.delete.view"}
    assert actions(section="approvals") == set()
    assert client.get("/school-admin/audit-log", params={"section": "nope"}, headers=_headers("admin_a")).status_code == 400


def test_another_schools_admin_sees_none_of_it(api):
    client, db = api
    client.get("/school-admin/users", headers=_headers("admin_a"))
    client.get("/teacher/students", headers=_headers("tea1"))
    rows = client.get("/school-admin/audit-log", headers=_headers("admin_b")).json()
    assert [r["action"] for r in rows if r["actor"] in ("admin_a", "tea1")] == []


def test_a_failure_to_write_the_log_never_breaks_the_page(api, monkeypatch):
    client, db = api
    monkeypatch.setattr(audit, "AuditLog", None)   # any use of it now raises inside log_view
    assert client.get("/school-admin/users", headers=_headers("admin_a")).status_code == 200
