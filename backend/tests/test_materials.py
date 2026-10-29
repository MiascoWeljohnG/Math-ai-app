"""Teachers see only the files they uploaded; the school admin sees every file of their school, with who uploaded it and when."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from database import get_db
from models import Material, School, User
from routes import school_admin_routes, teacher_routes


@pytest.fixture
def api(db, rag):
    school = School(name="School A")
    db.add(school)
    db.flush()
    ana = User(username="ana", first_name="Ana", last_name="Reyes", password_hash="x", role="teacher", school_id=school.id)
    ben = User(username="ben", password_hash="x", role="teacher", school_id=school.id)
    boss = User(username="admin_a", password_hash="x", role="school_admin", school_id=school.id)
    student = User(username="stu", password_hash="x", role="user", school_id=school.id)
    db.add_all([ana, ben, boss, student])
    db.add_all([
        Material(filename="a/1_old.pdf", display_name="old.pdf", branch="Algebra", uploaded_by="ana", school_id=school.id, uploaded_at=datetime(2026, 1, 1, 8, 0)),
        Material(filename="a/2_new.pdf", display_name="new.pdf", branch="Geometry", uploaded_by="ana", school_id=school.id, uploaded_at=datetime(2026, 2, 1, 8, 0)),
        Material(filename="b/3_ben.pdf", display_name="ben.pdf", branch="General", uploaded_by="ben", school_id=school.id, uploaded_at=datetime(2026, 3, 1, 8, 0)),
        Material(filename="l/4_legacy.txt", display_name="legacy.txt", branch="General", uploaded_by="legacy", school_id=school.id, uploaded_at=datetime(2026, 4, 1, 8, 0)),
    ])
    db.commit()
    app, current = FastAPI(), {"user": ana}
    app.include_router(teacher_routes.router)
    app.include_router(school_admin_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    return SimpleNamespace(client=TestClient(app), current=current, ana=ana, ben=ben, admin=boss, student=student)


def test_teacher_sees_only_their_own_files_newest_first(api):
    rows = api.client.get("/teacher/files").json()
    assert [r["display_name"] for r in rows] == ["new.pdf", "old.pdf"]
    assert rows[0]["uploaded_at"] == "2026-02-01T08:00:00Z"   # the Z lets the browser show local time
    api.current["user"] = api.ben
    assert [r["display_name"] for r in api.client.get("/teacher/files").json()] == ["ben.pdf"]


def test_school_admin_sees_every_file_with_uploader_and_date(api):
    api.current["user"] = api.admin
    rows = api.client.get("/school-admin/files").json()
    assert [r["display_name"] for r in rows] == ["legacy.txt", "ben.pdf", "new.pdf", "old.pdf"]
    by_name = {r["display_name"]: r for r in rows}
    assert by_name["new.pdf"]["uploaded_by"] == "ana" and by_name["new.pdf"]["uploaded_by_name"] == "Ana Reyes"
    assert by_name["ben.pdf"]["uploaded_by_name"] == ""            # account has no name filled in
    assert by_name["legacy.txt"]["uploaded_by"] == "legacy"        # uploads from before tracking existed
    assert by_name["old.pdf"]["uploaded_at"] == "2026-01-01T08:00:00Z"


def test_only_the_right_role_can_list_files(api):
    api.current["user"] = api.ana
    assert api.client.get("/school-admin/files").status_code == 403       # teachers can't see everyone's files
    api.current["user"] = api.student
    assert api.client.get("/teacher/files").status_code == 403
    assert api.client.get("/school-admin/files").status_code == 403
