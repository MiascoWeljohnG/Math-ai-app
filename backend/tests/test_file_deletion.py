"""A teacher deleting a file they uploaded sends it to the archive; the old ask-and-approve requests can still be answered by the admin of their school."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import create_access_token, hash_password
from database import get_db
from models import ACTIVE, ArchivedItem, AuditLog, FileDeletionRequest, Material, Notification, School, User
from routes import archive_routes, file_deletion_routes, school_admin_routes


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
    app.include_router(archive_routes.router)
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


def _legacy_request(db, filename="f1", who="tea1"):
    """A deletion request made before the archive existed: still waiting for the school admin."""
    school = db.query(School).filter(School.name == "School A").one()
    row = FileDeletionRequest(filename=filename, display_name="Matrices.pptx", requested_by=who, school_id=school.id, reason="uploaded twice")
    db.add(row)
    db.commit()
    return row.id


def test_teacher_delete_moves_the_file_to_the_archive(api, rag):
    client, db = api
    response = _ask(client)
    assert response.status_code == 200 and response.json()["status"] == "archived"
    assert db.query(Material).filter(Material.filename == "f1").first() is None          # gone from the app at once
    assert "f1" in rag.deleted_chunks                                                     # and the AI stops using it
    item = db.query(ArchivedItem).one()
    assert (item.kind, item.title, item.context, item.archived_by, item.reason) == ("file", "Matrices.pptx", "Linear Algebra", "tea1", "uploaded twice")
    assert db.query(AuditLog).filter(AuditLog.action == "file.archive", AuditLog.actor == "tea1").count() == 1
    assert db.query(Notification).filter(Notification.admin_username == "admin_a", Notification.kind == "item_archived").count() == 1
    assert db.query(Notification).filter(Notification.admin_username == "admin_b").count() == 0   # the other school hears nothing


def test_a_local_original_is_kept_in_the_archive_until_it_is_deleted_for_good(api, tmp_path, monkeypatch):
    client, db = api
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(config, "CHROMA_VAULT_DIR", str(uploads))
    original = uploads / "Uploaded Materials" / "Algebra" / "x.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"%PDF")
    db.add(Material(filename="Uploaded Materials/Algebra/x.pdf", display_name="x.pdf", branch="Algebra", uploaded_by="tea1",
                    school_id=db.query(School).filter(School.name == "School A").one().id))
    db.commit()
    assert _ask(client, filename="Uploaded Materials/Algebra/x.pdf").status_code == 200
    kept = tmp_path / "archived_uploads" / "Uploaded Materials" / "Algebra" / "x.pdf"
    assert not original.exists() and kept.read_bytes() == b"%PDF"        # moved out of the folder the AI indexes, not erased
    item = db.query(ArchivedItem).one()
    item.archived_at = item.archived_at - timedelta(days=31)
    db.commit()
    assert client.post(f"/archive/{item.id}/purge", headers=_headers("admin_a")).status_code == 200
    assert not kept.exists() and db.query(ArchivedItem).count() == 0


def test_only_the_uploader_can_delete_a_file(api):
    client, db = api
    assert _ask(client, who="tea1", filename="f2").status_code == 404      # someone else's file
    assert _ask(client, who="admin_a").status_code == 403                  # the admin has their own delete, this route is the teacher's
    assert _ask(client).status_code == 200
    assert _ask(client).status_code == 404                                 # already in the archive


def test_a_teacher_archiving_a_file_closes_an_old_request_for_it(api):
    client, db = api
    old = _legacy_request(db)
    assert _ask(client).status_code == 200
    assert db.query(FileDeletionRequest).filter(FileDeletionRequest.id == old).one().status == "approved"   # nothing left to decide


# ---- requests made before the archive existed are still answered by the school's admin ----
def test_a_teacher_cannot_decide_or_read_the_queue(api):
    client, db = api
    request_id = _legacy_request(db)
    assert client.post(f"/file-deletions/{request_id}/decision", json={"approve": True}, headers=_headers("tea1")).status_code == 403
    assert client.get("/file-deletions", headers=_headers("tea1")).status_code == 403
    assert db.query(Material).filter(Material.filename == "f1").first() is not None


def test_approving_an_old_request_deletes_the_file_everywhere(api, rag):
    client, db = api
    _legacy_request(db)
    queue = client.get("/file-deletions", headers=_headers("admin_a")).json()
    assert [(r["display_name"], r["requested_by"], r["reason"]) for r in queue] == [("Matrices.pptx", "tea1", "uploaded twice")]
    response = client.post(f"/file-deletions/{queue[0]['id']}/decision", json={"approve": True}, headers=_headers("admin_a"))
    assert response.status_code == 200 and response.json()["status"] == "approved"
    assert db.query(Material).filter(Material.filename == "f1").first() is None
    assert "f1" in rag.deleted_chunks                                       # what the AI learned from it is gone too
    assert db.query(AuditLog).filter(AuditLog.action == "file.delete.approve").count() == 1
    assert client.get("/file-deletions", headers=_headers("admin_a")).json() == []
    assert client.post(f"/file-deletions/{queue[0]['id']}/decision", json={"approve": True}, headers=_headers("admin_a")).status_code == 409


def test_rejecting_an_old_request_keeps_the_file_and_tells_the_teacher(api):
    client, db = api
    request_id = _legacy_request(db)
    assert client.post(f"/file-deletions/{request_id}/decision", json={"approve": False}, headers=_headers("admin_a")).json()["status"] == "rejected"
    assert db.query(Material).filter(Material.filename == "f1").first() is not None
    assert client.get("/file-deletions/mine", headers=_headers("tea1")).json() == [{"filename": "f1", "status": "rejected"}]


def test_another_schools_admin_cannot_decide(api):
    client, db = api
    request_id = _legacy_request(db)
    assert client.post(f"/file-deletions/{request_id}/decision", json={"approve": True}, headers=_headers("admin_b")).status_code == 404
    assert db.query(Material).filter(Material.filename == "f1").first() is not None


def test_old_requests_count_in_the_admins_overview(api):
    client, db = api
    assert client.get("/school-admin/overview", headers=_headers("admin_a")).json()["attention"]["deletions"] == 0
    _legacy_request(db)
    assert client.get("/school-admin/overview", headers=_headers("admin_a")).json()["attention"]["deletions"] == 1
