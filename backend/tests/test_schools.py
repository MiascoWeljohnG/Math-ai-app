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
from routes import (admin_routes, auth_routes, learning_routes, materials_routes, school_admin_routes,
                    schools_routes, subject_deletion_routes, subjects_routes, teacher_routes)

BIRTHDAY = "1990-01-01"


@pytest.fixture
def api(db, rag, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROMA_VAULT_DIR", str(tmp_path))
    app, current = FastAPI(), {"user": None}
    for module in (admin_routes, auth_routes, learning_routes, materials_routes, school_admin_routes,
                   schools_routes, subject_deletion_routes, subjects_routes, teacher_routes):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    return SimpleNamespace(client=TestClient(app), current=current, db=db, users={}, tmp=tmp_path)


def person(api, username, role, school=None):
    user = User(username=username, password_hash="x", role=role, school_id=school.id if school else None)
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
    return {"username": username, "first_name": "F", "last_name": "L", "email": "a@b.co",
            "birthday": BIRTHDAY, "password": "secret1", "school_id": school_id}


def two_schools(api):
    """School A and B, each with a teacher, a student and an admin, plus the main admin."""
    a, b = school(api, "School A"), school(api, "School B")
    person(api, "admin", "admin")
    for tag, sch in (("a", a), ("b", b)):
        person(api, f"t_{tag}", "teacher", sch)
        person(api, f"s_{tag}", "user", sch)
        person(api, f"adm_{tag}", "school_admin", sch)
    return a, b


# ---------------------------------------------------------------- the main admin adds schools and accounts
def test_main_admin_adds_a_school_with_the_starting_subjects(api):
    person(api, "admin", "admin")
    as_(api, "admin")
    res = api.client.post("/schools", json={"name": "  School   A "})
    assert res.status_code == 200 and res.json()["name"] == "School A"
    names = [s.name for s in api.db.query(Subject).filter(Subject.school_id == res.json()["id"])]
    assert names == ["Algebra", "Geometry", "Statistics", "Calculus"]
    assert api.client.post("/schools", json={"name": "school a"}).status_code == 409
    assert api.client.get("/schools").json() == [{"id": res.json()["id"], "name": "School A"}]


def test_only_the_main_admin_adds_schools(api):
    a, _ = two_schools(api)
    for name in ("t_a", "adm_a", "s_a"):
        as_(api, name)
        assert api.client.post("/schools", json={"name": "School C"}).status_code == 403


def test_admin_and_teacher_accounts_are_made_for_a_school(api):
    a, b = two_schools(api)
    as_(api, "admin")
    made = api.client.post("/admin/create-admin", json=account("new_adm", a.id))
    assert made.status_code == 200 and "School A admin" in made.json()["message"]
    row = api.db.query(User).filter(User.username == "new_adm").one()
    assert (row.role, row.school_id) == ("school_admin", a.id)

    api.client.post("/admin/create-admin", json=account("main2"))   # no school: another main admin
    row = api.db.query(User).filter(User.username == "main2").one()
    assert (row.role, row.school_id) == ("admin", None)

    assert api.client.post("/admin/create-teacher", json=account("new_t", b.id)).status_code == 200
    row = api.db.query(User).filter(User.username == "new_t").one()
    assert (row.role, row.school_id) == ("teacher", b.id)
    assert api.client.post("/admin/create-teacher", json=account("bad_t", 9999)).status_code == 400

    users = {u["username"]: u["school"] for u in api.client.get("/admin/users").json()}
    assert users["new_t"] == "School B" and users["admin"] is None


def test_only_the_default_admin_creates_admins(api):
    two_schools(api)
    person(api, "boss", "admin")
    as_(api, "boss")
    assert api.client.post("/admin/create-admin", json=account("x")).status_code == 403
    as_(api, "adm_a")
    assert api.client.post("/admin/create-admin", json=account("x")).status_code == 403   # a school admin is not a main admin


# ---------------------------------------------------------------- sign up and log in
def test_students_pick_a_school_once_schools_exist(api):
    form = {"student_id": "2024-1", "full_name": "Ana Cruz", "email": "a@b.co", "birthday": BIRTHDAY, "password": "secret1"}
    assert api.client.post("/auth/register", json=form).status_code == 200   # no schools yet: as before
    assert api.db.query(User).filter(User.username == "2024-1").one().school_id is None

    a = school(api, "School A")
    form["student_id"] = "2024-2"
    assert api.client.post("/auth/register", json=form).status_code == 400                       # school missing
    assert api.client.post("/auth/register", json={**form, "school_id": 999}).status_code == 400   # school unknown
    assert api.client.post("/auth/register", json={**form, "school_id": a.id}).status_code == 200
    login = api.client.post("/auth/login", json={"username": "2024-2", "password": "secret1"}).json()
    assert (login["role"], login["school_id"], login["school_name"]) == ("user", a.id, "School A")


# ---------------------------------------------------------------- the school admin's own page
def test_school_admin_only_reaches_their_own_school(api):
    a, b = two_schools(api)
    as_(api, "adm_a")
    assert {u["username"] for u in api.client.get("/school-admin/users").json()} == {"t_a", "s_a", "adm_a"}

    # the school comes from their account: a school_id in the body is ignored
    assert api.client.post("/school-admin/create-teacher", json=account("t_new", b.id)).status_code == 200
    assert api.db.query(User).filter(User.username == "t_new").one().school_id == a.id

    assert api.client.get("/admin/users").status_code == 403   # not a main admin
    as_(api, "admin")
    assert api.client.get("/school-admin/users").status_code == 403   # the main admin has no school
    as_(api, "t_a")
    assert api.client.get("/school-admin/users").status_code == 403


def test_teachers_only_see_their_schools_students(api):
    two_schools(api)
    for tag in ("a", "b"):
        as_(api, f"t_{tag}")
        assert [s["username"] for s in api.client.get("/teacher/students").json()] == [f"s_{tag}"]


# ---------------------------------------------------------------- subjects, files, reminders, deletions
def test_subjects_are_separate_per_school(api):
    a, b = two_schools(api)
    ids = {}
    for tag in ("a", "b"):
        as_(api, f"t_{tag}")   # the same name is fine in two schools, not twice in one
        res = api.client.post("/subjects/shared", json={"name": "Calculus II"})
        assert res.status_code == 200
        ids[tag] = res.json()["id"]
        assert api.client.post("/subjects/shared", json={"name": "calculus ii"}).status_code == 409
    assert ids["a"] != ids["b"]

    as_(api, "s_a")
    assert [s["id"] for s in api.client.get("/subjects").json()] == [ids["a"]]
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

    as_(api, "admin")   # the main admin lists every school's files, so they can open them all too
    assert api.client.get(f"/materials/{path}/file").status_code == 200


def test_reminders_for_everyone_stay_in_the_school(api):
    two_schools(api)
    as_(api, "t_a")
    assert api.client.post("/learning/reminders", json={"message": "Quiz Friday"}).status_code == 200
    assert api.client.post("/learning/reminders", json={"message": "Hi", "student_username": "s_b"}).status_code == 404
    as_(api, "s_a")
    assert [r["message"] for r in api.client.get("/learning/reminders").json()] == ["Quiz Friday"]
    as_(api, "s_b")
    assert api.client.get("/learning/reminders").json() == []


def test_deletion_requests_are_listed_per_school_and_the_main_admin_sees_all(api):
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
    assert [r["subject_name"] for r in api.client.get("/subject-deletions").json()] == ["Algebra"]
    as_(api, "admin")
    assert len(api.client.get("/subject-deletions").json()) == 1


# ---------------------------------------------------------------- registered student numbers
def test_admin_registers_student_numbers_and_signup_follows_the_list(api):
    a, b = two_schools(api)
    form = {"full_name": "Ana Cruz", "email": "a@b.co", "birthday": BIRTHDAY, "password": "secret1"}
    assert api.client.get("/schools/signup-mode").json() == {"registry": False}   # no list yet: students pick a school

    as_(api, "admin")
    res = api.client.post("/admin/registered-students", json={"numbers": "2024-1, 2024-2\n2024-2\n2024-3 ba!d", "school_id": a.id})
    assert res.json()["added"] == 3   # a number repeated inside the pasted list counts once
    assert res.json()["skipped"] == [{"number": "ba!d", "reason": "not a valid student number"}]
    again = api.client.post("/admin/registered-students", json={"numbers": "2024-1 2024-9", "school_id": b.id}).json()
    assert again["added"] == 1 and again["skipped"] == [{"number": "2024-1", "reason": "already registered"}]
    assert api.client.post("/admin/registered-students", json={"numbers": "  "}).status_code == 400
    assert api.client.post("/admin/registered-students", json={"numbers": "x1", "school_id": 999}).status_code == 400
    assert api.client.get("/schools/signup-mode").json() == {"registry": True}

    # only listed numbers sign up, and the school comes from the list, whatever the form says
    assert api.client.post("/auth/register", json={**form, "student_id": "9999"}).status_code == 400
    ok = api.client.post("/auth/register", json={**form, "student_id": "2024-1", "school_id": b.id})
    assert ok.status_code == 200
    assert api.db.query(User).filter(User.username == "2024-1").one().school_id == a.id
    assert api.client.post("/auth/register", json={**form, "student_id": "2024-1"}).status_code == 400   # already has an account

    rows = {r["student_number"]: r for r in api.client.get("/admin/registered-students").json()}
    assert rows["2024-1"]["signed_up"] and rows["2024-1"]["school"] == "School A"
    assert not rows["2024-9"]["signed_up"] and rows["2024-9"]["school"] == "School B"
    assert api.client.delete(f"/admin/registered-students/{rows['2024-1']['id']}").status_code == 400   # signed up already
    assert api.client.delete(f"/admin/registered-students/{rows['2024-9']['id']}").status_code == 200
    as_(api, "t_a")
    assert api.client.get("/admin/registered-students").status_code == 403


def test_school_admin_registers_students_for_their_own_school_only(api):
    a, b = two_schools(api)
    as_(api, "adm_a")
    assert api.client.post("/school-admin/registered-students", json={"numbers": "A-1 A-2", "school_id": b.id}).json()["added"] == 2
    as_(api, "adm_b")
    api.client.post("/school-admin/registered-students", json={"numbers": "B-1"})
    assert [r["student_number"] for r in api.client.get("/school-admin/registered-students").json()] == ["B-1"]

    as_(api, "adm_a")
    mine = {r["student_number"]: r for r in api.client.get("/school-admin/registered-students").json()}
    assert set(mine) == {"A-1", "A-2"} and mine["A-1"]["school"] == "School A"
    as_(api, "adm_b")
    assert api.client.delete(f"/school-admin/registered-students/{mine['A-1']['id']}").status_code == 404   # not their school
    as_(api, "adm_a")
    assert api.client.delete(f"/school-admin/registered-students/{mine['A-1']['id']}").status_code == 200
