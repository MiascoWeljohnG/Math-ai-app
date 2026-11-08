"""A teacher can only ASK to delete a file they uploaded; the admin of their school decides."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import create_access_token, hash_password
from database import get_db
from models import ACTIVE, AuditLog, FileDeletionRequest, Material, Notification, School, User
from routes import file_deletion_routes, school_admin_routes


def _user(db, username, role, school):
    u = User(username=username, password_hash=hash_password("Password-123"), role=role, status=ACTIVE, school_id=school.id)
    db.add(u)
    return u


def _headers(username):
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


@pytest.fixture
def api(db, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))
    app = FastAPI()
    app.include_router(file_deletion_routes.router)
    app.include_router(school_admin_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    for name, role, school in [("admin_a", "school_admin", a), ("tea1", "teacher", a), ("tea2", "teacher", a), ("admin_b", "school_admin", b)]:
        _user(db, name, role, school)
    db.add_all([
        Material(filename="f1", display_name="Matrices.pptx", branch="Linear Algebra", uploaded_by="tea1", school_id=a.id),
        Material(filename="f2", display_name="Other.pdf", branch="Algebra", uploaded_by="tea2", school_id=a.id),
    ])
    db.commit()
    return TestClient(app), db


def _ask(client, who="tea1", filename="f1", reason="uploaded twice"):
    return client.post("/file-deletions", json={"filename": filename, "reason": reason}, headers=_headers(who))


def test_teacher_request_waits_for_the_admin_and_the_file_stays(api):
    client, db = api
    response = _ask(client)
    assert response.status_code == 200 and response.json()["status"] == "pending"
    assert db.query(Material).filter(Material.filename == "f1").first() is not None          # nothing deleted yet
    assert db.query(Notification).filter(Notification.admin_username == "admin_a", Notification.kind == "file_deletion_request").count() == 1
    assert db.query(Notification).filter(Notification.admin_username == "admin_b").count() == 0   # the other school hears nothing
    assert client.get("/file-deletions/mine", headers=_headers("tea1")).json() == [{"filename": "f1", "status": "pending"}]


def test_only_the_uploader_can_ask_and_only_once(api):
    client, db = api
    assert _ask(client, who="tea1", filename="f2").status_code == 404      # someone else's file
    assert _ask(client, who="admin_a").status_code == 403                  # the admin decides, they do not ask here
    assert _ask(client).status_code == 200
    assert _ask(client).status_code == 409                                 # already waiting


def test_a_teacher_cannot_decide_or_read_the_queue(api):
    client, db = api
    _ask(client)
    request_id = db.query(FileDeletionRequest).first().id
    assert client.post(f"/file-deletions/{request_id}/decision", json={"approve": True}, headers=_headers("tea1")).status_code == 403
    assert client.get("/file-deletions", headers=_headers("tea1")).status_code == 403
    assert db.query(Material).filter(Material.filename == "f1").first() is not None


def test_approving_deletes_the_file_everywhere(api, rag):
    client, db = api
    _ask(client)
    queue = client.get("/file-deletions", headers=_headers("admin_a")).json()
    assert [(r["display_name"], r["requested_by"], r["reason"]) for r in queue] == [("Matrices.pptx", "tea1", "uploaded twice")]
    response = client.post(f"/file-deletions/{queue[0]['id']}/decision", json={"approve": True}, headers=_headers("admin_a"))
    assert response.status_code == 200 and response.json()["status"] == "approved"
    assert db.query(Material).filter(Material.filename == "f1").first() is None
    assert "f1" in rag.deleted_chunks                                       # what the AI learned from it is gone too
    assert db.query(AuditLog).filter(AuditLog.action == "file.delete.approve").count() == 1
    assert client.get("/file-deletions", headers=_headers("admin_a")).json() == []
    assert client.get("/file-deletions/mine", headers=_headers("tea1")).json() == []
    assert client.post(f"/file-deletions/{queue[0]['id']}/decision", json={"approve": True}, headers=_headers("admin_a")).status_code == 409


def test_rejecting_keeps_the_file_and_tells_the_teacher(api):
    client, db = api
    _ask(client)
    request_id = db.query(FileDeletionRequest).first().id
    assert client.post(f"/file-deletions/{request_id}/decision", json={"approve": False}, headers=_headers("admin_a")).json()["status"] == "rejected"
    assert db.query(Material).filter(Material.filename == "f1").first() is not None
    assert client.get("/file-deletions/mine", headers=_headers("tea1")).json() == [{"filename": "f1", "status": "rejected"}]
    assert _ask(client).status_code == 200                                  # they may ask again after a decline


def test_another_schools_admin_cannot_decide(api):
    client, db = api
    _ask(client)
    request_id = db.query(FileDeletionRequest).first().id
    assert client.post(f"/file-deletions/{request_id}/decision", json={"approve": True}, headers=_headers("admin_b")).status_code == 404
    assert db.query(Material).filter(Material.filename == "f1").first() is not None


def test_waiting_requests_count_in_the_admins_overview(api):
    client, db = api
    assert client.get("/school-admin/overview", headers=_headers("admin_a")).json()["attention"]["deletions"] == 0
    _ask(client)
    assert client.get("/school-admin/overview", headers=_headers("admin_a")).json()["attention"]["deletions"] == 1
