"""Deleting a shared subject needs every admin's approval; lessons can be generated from an uploaded
file, creating a new branch when the AI says the file doesn't fit an existing one."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import classifier
import config
from auth import get_current_user
from database import get_db
from models import Lesson, LessonCompletion, LessonQuiz, Material, Subject, SubjectDeletionRequest, User
from routes import subject_deletion_routes, subjects_routes

NAMES = ["Algebra", "Geometry"]


@pytest.fixture
def api(db, rag, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROMA_VAULT_DIR", str(tmp_path))
    users = {
        "ana": User(username="ana", password_hash="x", role="teacher"),
        "root": User(username="root", password_hash="x", role="admin"),
        "boss": User(username="boss", password_hash="x", role="admin"),
        "stu": User(username="stu", password_hash="x", role="user"),
    }
    db.add_all(users.values())
    algebra, geometry = Subject(name="Algebra", description="Equations"), Subject(name="Geometry")
    db.add_all([algebra, geometry])
    db.commit()
    lesson = Lesson(subject_id=algebra.id, title="Intro", content="body", created_by="ana")
    db.add(lesson)
    db.commit()
    db.add_all([LessonQuiz(lesson_id=lesson.id, questions="[]"), LessonCompletion(user_id=users["stu"].id, lesson_id=lesson.id)])
    folder = tmp_path / "Uploaded Materials" / "General"
    folder.mkdir(parents=True)
    (folder / "primes.txt").write_text("Prime numbers and divisibility.")
    db.add(Material(filename="Uploaded Materials/General/primes.txt", display_name="primes.txt", branch="General", uploaded_by="ana"))
    db.commit()

    app, current = FastAPI(), {"user": users["ana"]}
    app.include_router(subject_deletion_routes.router)
    app.include_router(subjects_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    return SimpleNamespace(client=TestClient(app), current=current, users=users, algebra=algebra, geometry=geometry, db=db, rag=rag)


def as_user(api, name):
    api.current["user"] = api.users[name]


def subject_exists(api, subject):
    api.db.expire_all()
    return api.db.query(Subject).filter(Subject.id == subject.id).first() is not None


# ---------------------------------------------------------------- deletion needs every admin
def test_request_is_pending_and_subject_stays(api):
    res = api.client.post("/subject-deletions", json={"subject_id": api.algebra.id, "reason": "duplicate"})
    assert res.status_code == 200 and res.json()["status"] == "pending"
    assert subject_exists(api, api.algebra)
    pending = api.client.get("/subject-deletions").json()
    assert pending[0]["subject_name"] == "Algebra" and pending[0]["lesson_count"] == 1
    assert pending[0]["waiting_on"] == ["boss", "root"] and pending[0]["approved_by"] == []


def test_second_request_for_same_subject_is_refused(api):
    api.client.post("/subject-deletions", json={"subject_id": api.algebra.id})
    assert api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).status_code == 409


def test_personal_or_missing_subjects_cannot_be_requested(api):
    mine = Subject(name="Mine", owner_user_id=api.users["stu"].id)
    api.db.add(mine)
    api.db.commit()
    assert api.client.post("/subject-deletions", json={"subject_id": mine.id}).status_code == 404
    assert api.client.post("/subject-deletions", json={"subject_id": 9999}).status_code == 404


def test_students_cannot_request_and_teachers_cannot_decide(api):
    as_user(api, "stu")
    assert api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).status_code == 403
    as_user(api, "ana")
    request_id = api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).json()["request_id"]
    assert api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True}).status_code == 403


def test_subject_is_deleted_only_after_all_admins_approve(api):
    request_id = api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).json()["request_id"]
    as_user(api, "root")
    first = api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True}).json()
    assert first["status"] == "pending" and subject_exists(api, api.algebra)
    as_user(api, "boss")
    last = api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True}).json()
    assert last["status"] == "approved" and not subject_exists(api, api.algebra)
    assert api.db.query(Lesson).count() == 0 and api.db.query(LessonQuiz).count() == 0
    assert api.db.query(LessonCompletion).count() == 0
    assert api.client.get("/subject-deletions").json() == []
    assert subject_exists(api, api.geometry)   # nothing else was touched


def test_one_rejection_keeps_the_subject(api):
    request_id = api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).json()["request_id"]
    as_user(api, "root")
    api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True})
    as_user(api, "boss")
    assert api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": False}).json()["status"] == "rejected"
    assert subject_exists(api, api.algebra)
    assert api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True}).status_code == 409   # already closed
    assert api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).status_code == 200            # may ask again


def test_admin_requester_counts_as_approved(api):
    as_user(api, "root")
    body = api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).json()
    assert body["status"] == "pending"
    assert api.client.get("/subject-deletions").json()[0]["approved_by"] == ["root"]
    as_user(api, "boss")
    request_id = body["request_id"]
    assert api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True}).json()["status"] == "approved"


def test_sole_admin_deletes_immediately(api):
    api.db.delete(api.users["boss"])
    api.db.commit()
    as_user(api, "root")
    assert api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).json()["status"] == "approved"
    assert not subject_exists(api, api.algebra)


def test_an_admin_added_later_must_approve_too(api):
    request_id = api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).json()["request_id"]
    api.users["late"] = User(username="late", password_hash="x", role="admin")
    api.db.add(api.users["late"])
    api.db.commit()
    for name in ("root", "boss"):
        as_user(api, name)
        status = api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True}).json()["status"]
    assert status == "pending" and subject_exists(api, api.algebra)
    as_user(api, "late")
    assert api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True}).json()["status"] == "approved"


def test_admin_can_change_their_vote_while_pending(api):
    request_id = api.client.post("/subject-deletions", json={"subject_id": api.algebra.id}).json()["request_id"]
    as_user(api, "root")
    api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": True})
    assert api.client.get("/subject-deletions").json()[0]["my_vote"] == "approve"
    assert api.client.post(f"/subject-deletions/{request_id}/decision", json={"approve": False}).json()["status"] == "rejected"
    assert api.db.query(SubjectDeletionRequest).one().status == "rejected"


# ---------------------------------------------------------------- AI picks (or creates) the branch
def choice(subject, confidence=90, new_name="NONE", is_math="YES"):
    return f"IS_MATH: {is_math}\nSUBJECT: {subject}\nCONFIDENCE: {confidence}\nNEW_NAME: {new_name}\nDESCRIPTION: About it."


@pytest.mark.parametrize("reply, action, subject", [
    (choice("Geometry"), "existing", "Geometry"),
    (choice("geometry ", 71), "existing", "Geometry"),                     # case and spaces don't matter
    (choice("Geometry", 69), "unclear", "Geometry"),                       # below the 70% rule
    (choice("NEW", 95, "Number Theory"), "new", None),
    (choice("NEW", 95, "algebra"), "existing", "Algebra"),                 # "new" name we already have
    (choice("NEW", 95), "unclear", None),                                  # NEW without a name
    (choice("Algebra", 90, is_math="NO"), "not_math", None),
    ("I think it is geometry", "unclear", None),
])
def test_parse_subject_choice(reply, action, subject):
    result = classifier.parse_subject_choice(reply, NAMES)
    assert result["action"] == action and result["subject"] == subject


def analyze(api, *replies):
    api.rag.reply = list(replies)
    return api.client.post("/subjects/analyze-material", json={"filename": "Uploaded Materials/General/primes.txt"})


def test_analyze_existing_subject_returns_titles(api):
    res = analyze(api, choice("Geometry"), "Angles\n1. Triangles\n- Circles")
    body = res.json()
    assert res.status_code == 200 and body["status"] == "existing" and body["subject_id"] == api.geometry.id
    assert body["titles"] == ["Angles", "Triangles", "Circles"]


def test_analyze_new_branch_saves_nothing(api):
    body = analyze(api, choice("NEW", 92, "Number Theory"), "Primes\nDivisibility").json()
    assert body["status"] == "new" and body["subject_name"] == "Number Theory" and body["subject_id"] is None
    assert api.db.query(Subject).filter(Subject.name == "Number Theory").count() == 0


def test_analyze_not_math_and_model_failure(api):
    assert analyze(api, choice("Algebra", is_math="NO")).json() == {"status": "not_math", "titles": []}
    assert analyze(api, RuntimeError("model down")).status_code == 502


def test_analyze_unknown_file_is_404(api):
    assert api.client.post("/subjects/analyze-material", json={"filename": "nope.pdf"}).status_code == 404


def test_new_branch_then_lesson_generated_from_the_file(api):
    created = api.client.post("/subjects/shared", json={"name": "Number Theory", "description": "Primes"})
    assert created.status_code == 200 and not created.json()["is_personal"]
    api.rag.reply = "## Primes\nA prime has exactly two divisors."
    res = api.client.post(
        f"/subjects/{created.json()['id']}/lessons/generate-from-material",
        json={"filename": "Uploaded Materials/General/primes.txt", "topic": "Primes"},
    )
    assert res.status_code == 200 and res.json()["title"] == "Primes"
    assert api.db.query(Lesson).filter(Lesson.title == "Primes").one().subject_id == created.json()["id"]


def test_shared_subject_names_are_unique_and_teacher_only(api):
    assert api.client.post("/subjects/shared", json={"name": "ALGEBRA"}).status_code == 409
    as_user(api, "stu")
    assert api.client.post("/subjects/shared", json={"name": "Whatever"}).status_code == 403
    assert api.client.post("/subjects/analyze-material", json={"filename": "x"}).status_code == 403
