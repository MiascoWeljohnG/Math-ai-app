"""A teacher can only ASK to delete a published lesson; the admin of their school decides, and every step is audited."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import create_access_token, hash_password
from database import get_db
from models import (
    ACTIVE, AuditLog, Lesson, LessonCompletion, LessonDeletionRequest, LessonQuiz, Notification, School, Subject, User,
)
from routes import lesson_deletion_routes, school_admin_routes, subjects_routes


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
    app.include_router(lesson_deletion_routes.router)
    app.include_router(school_admin_routes.router)
    app.include_router(subjects_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    for name, role, school in [("admin_a", "school_admin", a), ("tea1", "teacher", a), ("admin_b", "school_admin", b), ("stu1", "user", a)]:
        _user(db, name, role, school)
    algebra = Subject(name="Algebra", owner_user_id=None, school_id=a.id)
    db.add(algebra)
    db.flush()
    live = Lesson(subject_id=algebra.id, title="Linear equations", content="x", created_by="tea1", status="published")
    draft = Lesson(subject_id=algebra.id, title="Quadratics (draft)", content="x", created_by="tea1", status="draft")
    db.add_all([live, draft])
    db.flush()
    db.add_all([LessonQuiz(lesson_id=live.id, questions="[]"), LessonCompletion(user_id=1, lesson_id=live.id)])
    db.commit()
    return TestClient(app), db, algebra, live, draft


def _ask(client, subject, lesson, who="tea1", reason="duplicate of lesson 2"):
    return client.post("/lesson-deletions", json={"subject_id": subject.id, "lesson_id": lesson.id, "reason": reason}, headers=_headers(who))


def test_teacher_request_waits_for_the_admin_and_the_lesson_stays(api):
    client, db, subject, live, _ = api
    response = _ask(client, subject, live)
    assert response.status_code == 200 and response.json()["status"] == "pending"
    assert db.query(Lesson).filter(Lesson.id == live.id).first() is not None   # nothing deleted yet
    assert db.query(Notification).filter(Notification.admin_username == "admin_a", Notification.kind == "lesson_deletion_request").count() == 1
    assert db.query(Notification).filter(Notification.admin_username == "admin_b").count() == 0   # the other school hears nothing
    assert client.get("/lesson-deletions/mine", headers=_headers("tea1")).json() == [{"lesson_id": live.id, "status": "pending"}]
    log = db.query(AuditLog).filter(AuditLog.action == "lesson.delete.request").one()
    assert log.actor == "tea1" and "Linear equations" in log.target and log.detail == "duplicate of lesson 2"


def test_a_published_lesson_cannot_be_deleted_directly_by_a_teacher(api):
    client, db, subject, live, draft = api
    assert client.delete(f"/subjects/{subject.id}/lessons/{live.id}", headers=_headers("tea1")).status_code == 403
    assert db.query(Lesson).filter(Lesson.id == live.id).first() is not None
    # drafts are not live for students, so throwing one away needs no approval
    assert client.delete(f"/subjects/{subject.id}/lessons/{draft.id}", headers=_headers("tea1")).status_code == 200
    assert db.query(Lesson).filter(Lesson.id == draft.id).first() is None


def test_only_published_lessons_can_be_asked_about_and_only_once(api):
    client, db, subject, live, draft = api
    assert _ask(client, subject, draft).status_code == 400
    assert _ask(client, subject, live).status_code == 200
    assert _ask(client, subject, live).status_code == 409
    assert _ask(client, subject, live, who="admin_a").status_code == 403      # the admin decides, they do not ask
    assert _ask(client, subject, live, who="stu1").status_code == 403
    assert _ask(client, subject, live, who="admin_b").status_code == 403


def test_the_admins_approval_deletes_the_lesson_and_everything_under_it(api):
    client, db, subject, live, _ = api
    _ask(client, subject, live)
    queue = client.get("/lesson-deletions", headers=_headers("admin_a")).json()
    assert len(queue) == 1 and queue[0]["lesson_title"] == "Linear equations" and queue[0]["subject_name"] == "Algebra" and queue[0]["completions"] == 1
    lesson_id = live.id   # read before the delete: the row is gone afterwards
    assert client.post(f"/lesson-deletions/{queue[0]['id']}/decision", json={"approve": True}, headers=_headers("tea1")).status_code == 403
    response = client.post(f"/lesson-deletions/{queue[0]['id']}/decision", json={"approve": True}, headers=_headers("admin_a"))
    assert response.status_code == 200 and response.json()["status"] == "approved"
    assert db.query(Lesson).filter(Lesson.id == lesson_id).first() is None
    assert db.query(LessonQuiz).filter(LessonQuiz.lesson_id == lesson_id).count() == 0
    assert db.query(LessonCompletion).filter(LessonCompletion.lesson_id == lesson_id).count() == 0
    assert db.query(AuditLog).filter(AuditLog.action == "lesson.delete.approve", AuditLog.actor == "admin_a").count() == 1
    assert client.get("/lesson-deletions", headers=_headers("admin_a")).json() == []
    assert client.post(f"/lesson-deletions/{queue[0]['id']}/decision", json={"approve": True}, headers=_headers("admin_a")).status_code == 409


def test_a_rejection_keeps_the_lesson_and_the_teacher_is_told(api):
    client, db, subject, live, _ = api
    request_id = _ask(client, subject, live).json()["request_id"]
    assert client.post(f"/lesson-deletions/{request_id}/decision", json={"approve": False}, headers=_headers("admin_a")).json()["status"] == "rejected"
    assert db.query(Lesson).filter(Lesson.id == live.id).first() is not None
    assert db.query(AuditLog).filter(AuditLog.action == "lesson.delete.reject").count() == 1
    assert client.get("/lesson-deletions/mine", headers=_headers("tea1")).json() == [{"lesson_id": live.id, "status": "rejected"}]
    assert _ask(client, subject, live).status_code == 200                      # may ask again after a decline


def test_another_schools_admin_cannot_see_or_decide_the_request(api):
    client, db, subject, live, _ = api
    request_id = _ask(client, subject, live).json()["request_id"]
    assert client.get("/lesson-deletions", headers=_headers("admin_b")).json() == []
    assert client.post(f"/lesson-deletions/{request_id}/decision", json={"approve": True}, headers=_headers("admin_b")).status_code == 404
    assert db.query(Lesson).filter(Lesson.id == live.id).first() is not None


def test_a_request_for_a_lesson_that_is_already_gone_clears_itself(api):
    client, db, subject, live, _ = api
    _ask(client, subject, live)
    assert client.delete(f"/subjects/{subject.id}/lessons/{live.id}", headers=_headers("admin_a")).status_code == 200
    assert client.get("/lesson-deletions", headers=_headers("admin_a")).json() == []
    assert db.query(LessonDeletionRequest).one().status == "approved"


def test_the_school_admin_can_delete_a_lesson_directly_and_it_is_audited(api):
    client, db, subject, live, _ = api
    assert client.delete(f"/subjects/{subject.id}/lessons/{live.id}", headers=_headers("admin_a")).status_code == 200
    row = db.query(AuditLog).filter(AuditLog.action == "lesson.delete").one()
    assert row.actor == "admin_a" and "Linear equations" in row.target and row.school_id == subject.school_id


def test_lesson_requests_count_towards_the_admins_needs_attention_number(api):
    client, db, subject, live, _ = api
    before = client.get("/school-admin/overview", headers=_headers("admin_a")).json()["attention"]["deletions"]
    _ask(client, subject, live)
    assert client.get("/school-admin/overview", headers=_headers("admin_a")).json()["attention"]["deletions"] == before + 1
    actions = [r["action"] for r in client.get("/school-admin/audit-log", headers=_headers("admin_a")).json()]
    assert "lesson.delete.request" in actions
