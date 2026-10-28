"""Schools: accounts, subjects, files, reminders and deletion requests are separate per school, school
admins only reach their own school, and accounts made before schools existed (school_id None) keep working."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import get_current_user
from database import get_db
from models import Material, School, Subject, User
from routes import (auth_routes, learning_routes, materials_routes, school_admin_routes,
                    schools_routes, subject_deletion_routes, subjects_routes, teacher_routes)

BIRTHDAY = "1990-01-01"


@pytest.fixture
def api(db, rag, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROMA_VAULT_DIR", str(tmp_path))
    app, current = FastAPI(), {"user": None}
    for module in (auth_routes, learning_routes, materials_routes, school_admin_routes,
                   schools_routes, subject_deletion_routes, subjects_routes, teacher_routes):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    return SimpleNamespace(client=TestClient(app), current=current, db=db, users={}, tmp=tmp_path)


def person(api, username, role, school=None, status="active"):
    user = User(username=username, password_hash="x", role=role, school_id=school.id if school else None, status=status)
    api.db.add(user)
    api.db.commit()
    api.users[username] = user
    return user


def as_(api, name):
    api.current["user"] = api.users[name]


def school(api, name):
    row = School(name=name)
    api.db.add(row)
    api.db.commit()
    return row


def account(username, school_id=None):
    return {"username": username, "last_name": "L", "first_name": "F", "middle_name": "M", "email": "a@b.co",
            "birthday": BIRTHDAY, "password": "secret123", "school_id": school_id}


def two_schools(api):
    """School A and B, each with a teacher, a student and its one admin."""
    a, b = school(api, "School A"), school(api, "School B")
    for tag, sch in (("a", a), ("b", b)):
        person(api, f"t_{tag}", "teacher", sch)
        person(api, f"s_{tag}", "user", sch)
        person(api, f"adm_{tag}", "school_admin", sch)
    return a, b


# ---------------------------------------------------------------- the two schools and who makes accounts
def test_there_are_exactly_two_fixed_schools(api):
    from bootstrap import ensure_schools
    ensure_schools(api.db)
    ensure_schools(api.db)   # running it again changes nothing
    schools = api.db.query(School).order_by(School.id).all()
    assert [s.name for s in schools] == ["School A", "School B"]
    for s in schools:   # each starts with the usual subjects
        assert [x.name for x in api.db.query(Subject).filter(Subject.school_id == s.id)] == ["Algebra", "Geometry", "Statistics", "Calculus"]
    assert [s["name"] for s in api.client.get("/schools").json()] == ["School A", "School B"]

    person(api, "adm_x", "school_admin", schools[0])
    as_(api, "adm_x")
    assert api.client.post("/schools", json={"name": "School C"}).status_code == 405   # there is no route to add one
    with pytest.raises(ValueError):                                                    # ...and the database refuses it too
        api.db.add(School(name="School C"))
        api.db.commit()
    api.db.rollback()
    assert api.db.query(School).count() == 2


def test_school_admin_creates_teachers_for_their_own_school_only(api):
    a, b = two_schools(api)
    as_(api, "adm_a")
    assert api.client.post("/school-admin/create-teacher", json=account("new_t", b.id)).status_code == 200   # school_id in the body is ignored
    row = api.db.query(User).filter(User.username == "new_t").one()
    assert (row.role, row.school_id, row.status) == ("teacher", a.id, "active")
    assert api.client.post("/school-admin/create-teacher", json={**account("weak_t"), "password": "short"}).status_code == 400
    assert api.client.post("/school-admin/create-teacher", json=account("new_t")).status_code == 400   # username taken
    for name in ("t_a", "s_a"):   # only the school admin makes teachers
        as_(api, name)
        assert api.client.post("/school-admin/create-teacher", json=account("x")).status_code == 403


def test_there_is_no_way_to_create_an_admin(api):
    two_schools(api)
    for name in ("adm_a", "adm_b", "t_a", "s_a"):
        as_(api, name)
        for path in ("/admin/create-admin", "/school-admin/create-admin", "/admin/create-teacher", "/school-admin/create-school-admin"):
            assert api.client.post(path, json=account("x", 1)).status_code in (404, 405)
    assert api.db.query(User).filter(User.username == "x").first() is None
    assert api.db.query(User).filter(User.role.in_(["admin", "school_admin"])).count() == 2   # exactly one per school


# ---------------------------------------------------------------- sign up and log in

# ---------------------------------------------------------------- the school admin's own page
def test_school_admin_only_reaches_their_own_school(api):
    a, b = two_schools(api)
    as_(api, "adm_a")
    assert {u["username"] for u in api.client.get("/school-admin/users").json()} == {"t_a", "s_a", "adm_a"}

    # the school comes from their account: a school_id in the body is ignored
    assert api.client.post("/school-admin/create-teacher", json=account("t_new", b.id)).status_code == 200
    assert api.db.query(User).filter(User.username == "t_new").one().school_id == a.id

    assert api.client.get("/admin/users").status_code == 404   # the all-schools admin pages no longer exist
    as_(api, "t_a")
    assert api.client.get("/school-admin/users").status_code == 403


def test_teachers_only_see_their_schools_students(api):
    two_schools(api)
    for tag in ("a", "b"):
        as_(api, f"t_{tag}")
        assert [s["username"] for s in api.client.get("/teacher/students").json()] == [f"s_{tag}"]


# ---------------------------------------------------------------- subjects, files, reminders, deletions
def test_subjects_are_separate_per_school(api):
    # Use the app's fixed school names; arbitrary test schools are rejected by the model.
    from bootstrap import ensure_schools
    ensure_schools(api.db)
    schools = {row.name: row for row in api.db.query(School).all()}
    a = schools["Saint Mark's Institute"]
    b = schools["Cavite State University Bacoor Campus"]
    for tag, sch in (("a", a), ("b", b)):
        person(api, f"t_{tag}", "teacher", sch)
        person(api, f"s_{tag}", "user", sch)
        person(api, f"adm_{tag}", "school_admin", sch)
    ids = {}
    for tag in ("a", "b"):
        as_(api, f"t_{tag}")   # the same name is fine in two schools, not twice in one
        res = api.client.post("/subjects/shared", json={"name": "Calculus II"})
        assert res.status_code == 200
        ids[tag] = res.json()["id"]
        assert api.client.post("/subjects/shared", json={"name": "calculus ii"}).status_code == 409
    assert ids["a"] != ids["b"]

    as_(api, "s_a")
    expected_ids = [s.id for s in api.db.query(Subject).filter(Subject.school_id == a.id, Subject.owner_user_id.is_(None)).all()]
    assert [s["id"] for s in api.client.get("/subjects").json()] == expected_ids
    as_(api, "t_b")
    assert api.client.get(f"/subjects/{ids['a']}/lessons").status_code == 404
    lesson = {"title": "T", "content": "C"}
    assert api.client.post(f"/subjects/{ids['a']}/lessons", json=lesson).status_code == 404
    assert api.client.post(f"/subjects/{ids['b']}/lessons", json=lesson).status_code == 200

    person(api, "old_teacher", "teacher")   # made before schools existed: its own, separate pool
    as_(api, "old_teacher")
    assert api.client.get("/subjects").json() == []


def test_uploaded_files_are_separate_per_school(api):
    a, b = two_schools(api)
    folder = api.tmp / "Uploaded Materials" / "General"
    folder.mkdir(parents=True)
    (folder / "a.txt").write_text("Prime numbers and divisibility.")
    path = "Uploaded Materials/General/a.txt"
    api.db.add(Material(filename=path, display_name="a.txt", branch="General", uploaded_by="t_a", school_id=a.id))
    api.db.commit()

    as_(api, "t_a")
    assert [m["filename"] for m in api.client.get("/materials").json()] == [path]
    assert api.client.get(f"/materials/{path}/file").status_code == 200
    as_(api, "adm_a")
    assert [m["display_name"] for m in api.client.get("/school-admin/files").json()] == ["a.txt"]

    as_(api, "t_b")
    assert api.client.get("/materials").json() == []
    assert api.client.get(f"/materials/{path}/file").status_code == 404
    assert api.client.post("/subjects/analyze-material", json={"filename": path}).status_code == 404
    as_(api, "adm_b")
    assert api.client.get("/school-admin/files").json() == []


def test_school_admin_deletes_only_their_schools_files(api):
    a, b = two_schools(api)
    for name, sch in (("a.txt", a), ("b.txt", b)):
        api.db.add(Material(filename=f"Uploaded Materials/General/{name}", display_name=name, branch="General", uploaded_by="x", school_id=sch.id))
    api.db.commit()
    path_a, path_b = "Uploaded Materials/General/a.txt", "Uploaded Materials/General/b.txt"
    as_(api, "t_a")
    assert api.client.delete(f"/school-admin/files/{path_a}").status_code == 403
    as_(api, "adm_b")
    assert api.client.delete(f"/school-admin/files/{path_a}").status_code == 404   # another school's file
    as_(api, "adm_a")
    assert api.client.delete(f"/school-admin/files/{path_a}").status_code == 200
    assert [m.display_name for m in api.db.query(Material)] == ["b.txt"]
    assert api.client.delete(f"/school-admin/files/{path_b}").status_code == 404


def test_reminders_for_everyone_stay_in_the_school(api):
    two_schools(api)
    as_(api, "t_a")
    assert api.client.post("/learning/reminders", json={"message": "Quiz Friday"}).status_code == 200
    assert api.client.post("/learning/reminders", json={"message": "Hi", "student_username": "s_b"}).status_code == 404
    as_(api, "s_a")
    assert [r["message"] for r in api.client.get("/learning/reminders").json()] == ["Quiz Friday"]
    as_(api, "s_b")
    assert api.client.get("/learning/reminders").json() == []


def test_deletion_requests_are_per_school_and_the_schools_admin_decides(api):
    a, b = two_schools(api)
    subject = Subject(name="Algebra", school_id=a.id)
    api.db.add(subject)
    api.db.commit()
    as_(api, "t_a")
    assert api.client.post("/subject-deletions", json={"subject_id": subject.id}).status_code == 200
    as_(api, "t_b")
    assert api.client.post("/subject-deletions", json={"subject_id": subject.id}).status_code == 404   # not their subject
    assert api.client.get("/subject-deletions").json() == []
    as_(api, "t_a")
    request = api.client.get("/subject-deletions").json()[0]
    assert (request["subject_name"], request["waiting_on"], request["admins_total"]) == ("Algebra", ["adm_a"], 1)
    assert api.client.post(f"/subject-deletions/{request['id']}/decision", json={"approve": True}).status_code == 403   # a teacher cannot decide

    as_(api, "adm_b")   # the other school's admin cannot see or decide it
    assert api.client.get("/subject-deletions").json() == []
    assert api.client.post(f"/subject-deletions/{request['id']}/decision", json={"approve": True}).status_code == 404
    as_(api, "adm_a")
    assert api.client.post(f"/subject-deletions/{request['id']}/decision", json={"approve": True}).json()["status"] == "approved"
    assert api.db.query(Subject).filter(Subject.id == subject.id).first() is None
