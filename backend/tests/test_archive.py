"""The school admin's Archive and File deletion pages: what teachers deleted waits 30 days, only the admin of the same school sees it,
and only then can it be deleted for good (one by one or all at once)."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import archive
import config
import drive_storage
from auth import create_access_token, hash_password
from database import get_db
from models import ACTIVE, ArchivedItem, AuditLog, Lesson, Material, School, Subject, User
from routes import archive_routes, file_deletion_routes, lesson_deletion_routes, school_admin_routes, subject_deletion_routes, subjects_routes


def _headers(username):
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


@pytest.fixture
def api(db, rag, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))
    monkeypatch.setattr(config, "CHROMA_VAULT_DIR", str(tmp_path / "uploads"))
    app = FastAPI()
    for module in (archive_routes, file_deletion_routes, lesson_deletion_routes, subject_deletion_routes, school_admin_routes, subjects_routes):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: db
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    for name, role, school in [("admin_a", "school_admin", a), ("tea1", "teacher", a), ("stu1", "user", a), ("admin_b", "school_admin", b), ("tea_b", "teacher", b)]:
        db.add(User(username=name, password_hash=hash_password("Password-123"), role=role, status=ACTIVE, school_id=school.id))
    algebra = Subject(name="Algebra", school_id=a.id)
    db.add(algebra)
    db.flush()
    db.add(Lesson(subject_id=algebra.id, title="Linear equations", content="x", created_by="tea1", status="published"))
    db.add(Material(filename="f1", display_name="Matrices.pptx", branch="Linear Algebra", uploaded_by="tea1", school_id=a.id))
    db.commit()
    return TestClient(app), db, algebra


def _archive_everything(client, db, algebra):
    lesson = db.query(Lesson).one()
    assert client.post("/file-deletions", json={"filename": "f1"}, headers=_headers("tea1")).status_code == 200
    assert client.post("/lesson-deletions", json={"subject_id": algebra.id, "lesson_id": lesson.id}, headers=_headers("tea1")).status_code == 200
    assert client.post("/subject-deletions", json={"subject_id": algebra.id}, headers=_headers("tea1")).status_code == 200


def _age(db, kind, days):
    item = db.query(ArchivedItem).filter(ArchivedItem.kind == kind).one()
    item.archived_at = datetime.utcnow() - timedelta(days=days)
    db.commit()
    return item.id


def test_the_admin_sees_what_the_teacher_deleted_with_the_days_left(api):
    client, db, algebra = api
    _archive_everything(client, db, algebra)
    rows = client.get("/archive", headers=_headers("admin_a")).json()
    assert {r["kind"] for r in rows} == {"file", "lesson", "subject"}
    file_row = next(r for r in rows if r["kind"] == "file")
    assert (file_row["title"], file_row["context"], file_row["archived_by"], file_row["days_left"], file_row["due"]) == ("Matrices.pptx", "Linear Algebra", "tea1", 30, False)
    assert [r["kind"] for r in client.get("/archive?kind=lesson", headers=_headers("admin_a")).json()] == ["lesson"]
    assert client.get("/archive?kind=bogus", headers=_headers("admin_a")).status_code == 400


def test_only_the_admin_of_the_same_school_can_see_or_delete_it(api):
    client, db, algebra = api
    _archive_everything(client, db, algebra)
    item_id = _age(db, "file", 40)
    assert client.get("/archive", headers=_headers("admin_b")).json() == []                                   # the other school sees nothing
    assert client.post(f"/archive/{item_id}/purge", headers=_headers("admin_b")).status_code == 404
    for who in ("tea1", "stu1", "tea_b"):                                                                      # teachers and students have no access at all
        assert client.get("/archive", headers=_headers(who)).status_code == 403
        assert client.post(f"/archive/{item_id}/purge", headers=_headers(who)).status_code == 403
    assert db.query(ArchivedItem).count() == 3


def test_nothing_can_be_deleted_for_good_before_30_days(api):
    client, db, algebra = api
    _archive_everything(client, db, algebra)
    item_id = _age(db, "file", 29)
    response = client.post(f"/archive/{item_id}/purge", headers=_headers("admin_a"))
    assert response.status_code == 409 and "day" in response.json()["detail"]
    assert client.get("/archive?due=true", headers=_headers("admin_a")).json() == []
    assert client.post("/archive/purge-due", headers=_headers("admin_a")).json()["deleted"] == 0
    assert db.query(ArchivedItem).count() == 3


def test_after_30_days_the_item_is_listed_for_deletion_and_the_admin_deletes_it_for_good(api):
    client, db, algebra = api
    _archive_everything(client, db, algebra)
    item_id = _age(db, "lesson", 30)
    due = client.get("/archive?due=true", headers=_headers("admin_a")).json()
    assert [(r["kind"], r["title"], r["days_left"]) for r in due] == [("lesson", "Linear equations", 0)]
    assert len(client.get("/archive?due=false", headers=_headers("admin_a")).json()) == 2
    assert client.get("/school-admin/overview", headers=_headers("admin_a")).json()["attention"]["deletions"] == 1   # it needs the admin now
    assert client.post(f"/archive/{item_id}/purge", headers=_headers("admin_a")).status_code == 200
    assert db.query(ArchivedItem).filter(ArchivedItem.id == item_id).first() is None
    log = db.query(AuditLog).filter(AuditLog.action == "archive.purge").one()
    assert log.actor == "admin_a" and "Linear equations" in log.target
    assert client.post(f"/archive/{item_id}/purge", headers=_headers("admin_a")).status_code == 404


def test_delete_all_ready_only_touches_this_schools_expired_items(api):
    client, db, algebra = api
    _archive_everything(client, db, algebra)
    _age(db, "file", 45)
    _age(db, "subject", 31)
    result = client.post("/archive/purge-due", headers=_headers("admin_a")).json()
    assert result["deleted"] == 2 and result["failed"] == []
    assert [r["kind"] for r in client.get("/archive", headers=_headers("admin_a")).json()] == ["lesson"]       # the one still inside its 30 days stays


def test_a_drive_failure_keeps_the_item_in_the_archive(api, monkeypatch):
    client, db, algebra = api
    material = db.query(Material).one()
    material.drive_file_id = "drive-1"
    db.commit()
    monkeypatch.setattr(drive_storage, "archive_file", lambda file_id, school=None: None)
    assert client.post("/file-deletions", json={"filename": "f1"}, headers=_headers("tea1")).status_code == 200
    item_id = _age(db, "file", 31)

    def broken(file_id):
        raise drive_storage.DriveStorageError("Drive is unreachable")
    monkeypatch.setattr(drive_storage, "delete_file", broken)
    response = client.post(f"/archive/{item_id}/purge", headers=_headers("admin_a"))
    assert response.status_code == 502 and "Drive is unreachable" in response.json()["detail"]
    assert db.query(ArchivedItem).filter(ArchivedItem.id == item_id).count() == 1                              # can be retried

    deleted = []
    monkeypatch.setattr(drive_storage, "delete_file", lambda file_id: deleted.append(file_id))
    assert client.post("/archive/purge-due", headers=_headers("admin_a")).json()["deleted"] == 1
    assert deleted == ["drive-1"]


def test_expiry_arithmetic():
    item = ArchivedItem(kind="file", title="x", archived_by="t", archived_at=datetime(2026, 1, 1, 12, 0))
    assert archive.expires_at(item) == datetime(2026, 1, 31, 12, 0)
    assert archive.days_left(item, datetime(2026, 1, 1, 12, 0)) == 30
    assert archive.days_left(item, datetime(2026, 1, 30, 12, 1)) == 1                                          # part of a day counts as a day
    assert not archive.is_due(item, datetime(2026, 1, 31, 11, 59)) and archive.is_due(item, datetime(2026, 1, 31, 12, 0))
    assert archive.days_left(item, datetime(2026, 3, 1)) == 0
