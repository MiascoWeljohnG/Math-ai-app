import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from auth import hash_password, verify_password
from database import get_db
from models import ACTIVE, School, User
from routes import profile_routes


@pytest.fixture
def profile_api(db, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))
    app = FastAPI()
    app.include_router(profile_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    admin = User(username="admin_a", password_hash=hash_password("Current-pass-123"), role="school_admin", status=ACTIVE, school_id=a.id)
    other = User(username="taken", password_hash=hash_password("Current-pass-123"), role="school_admin", status=ACTIVE, school_id=b.id)
    db.add_all([admin, other])
    db.commit()
    from auth import create_access_token
    token = create_access_token({"sub": admin.username})
    return TestClient(app), db, admin, {"Authorization": f"Bearer {token}"}


def test_school_admin_can_update_own_profile_and_username(profile_api):
    client, db, admin, headers = profile_api
    res = client.put("/profile/account", headers=headers, json={
        "first_name": "Ada", "last_name": "Lovelace", "middle_name": "Byron",
        "email": "ada@example.com", "username": "ada_admin",
    })
    assert res.status_code == 200, res.text
    assert res.json()["username"] == "ada_admin"
    assert res.json()["display_name"] == "Ada Byron Lovelace"
    assert db.get(User, admin.id).username == "ada_admin"


def test_school_admin_account_update_rejects_taken_username(profile_api):
    client, db, admin, headers = profile_api
    res = client.put("/profile/account", headers=headers, json={
        "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com", "username": "taken",
    })
    assert res.status_code == 409
    db.refresh(admin)
    assert admin.username == "admin_a"


def test_school_admin_password_change_requires_current_password_and_updates_hash(profile_api):
    client, db, admin, headers = profile_api
    bad = client.put("/profile/password", headers=headers, json={"current_password": "wrong-password", "new_password": "New-strong-pass-123"})
    assert bad.status_code == 400
    good = client.put("/profile/password", headers=headers, json={"current_password": "Current-pass-123", "new_password": "New-strong-pass-123"})
    assert good.status_code == 200
    db.refresh(admin)
    assert verify_password("New-strong-pass-123", admin.password_hash)


def test_school_admin_cannot_change_username_without_authentication(profile_api):
    client, _, _, _ = profile_api
    res = client.put("/profile/account", json={"first_name": "Ada", "last_name": "Lovelace", "email": "a@example.com", "username": "ada_admin"})
    assert res.status_code == 401


def test_username_change_returns_token_that_still_works(profile_api):
    client, db, admin, headers = profile_api
    res = client.put("/profile/account", headers=headers, json={
        "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com", "username": "ada_admin",
    })
    assert res.status_code == 200, res.text
    fresh = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/profile", headers=fresh).status_code == 200
    # the old token was issued for the old username, so it no longer resolves
    assert client.get("/profile", headers=headers).status_code == 401


def _login(username):
    from auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


def test_teacher_can_edit_own_account_and_keeps_their_files_and_reminders(profile_api):
    from models import Material, Reminder, School
    client, db, admin, _ = profile_api
    teacher = User(username="t_old", password_hash=hash_password("Current-pass-123"), role="teacher", status=ACTIVE, school_id=admin.school_id)
    db.add(teacher)
    db.add(Material(filename="x_a.pdf", display_name="a.pdf", branch="Algebra", uploaded_by="t_old", school_id=admin.school_id))
    db.add(Reminder(message="Quiz Friday", created_by="t_old", school_id=admin.school_id))
    db.commit()

    res = client.put("/profile/account", headers=_login("t_old"), json={
        "first_name": "Tess", "last_name": "Teacher", "email": "tess@example.com", "username": "t_new"})
    assert res.status_code == 200, res.text
    assert res.json()["username"] == "t_new"
    # what the teacher uploaded / wrote is still theirs under the new username
    assert db.query(Material).filter(Material.uploaded_by == "t_new").count() == 1
    assert db.query(Material).filter(Material.uploaded_by == "t_old").count() == 0
    assert db.query(Reminder).filter(Reminder.created_by == "t_new").count() == 1
    # and the fresh token works while the old one no longer does
    fresh = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/profile", headers=fresh).status_code == 200
    assert client.get("/profile", headers=_login("t_old")).status_code == 401


def test_teacher_can_change_own_password(profile_api):
    client, db, admin, _ = profile_api
    teacher = User(username="t_pw", password_hash=hash_password("Current-pass-123"), role="teacher", status=ACTIVE, school_id=admin.school_id)
    db.add(teacher); db.commit()
    res = client.put("/profile/password", headers=_login("t_pw"), json={"current_password": "Current-pass-123", "new_password": "New-strong-pass-123"})
    assert res.status_code == 200, res.text
    db.refresh(teacher)
    assert verify_password("New-strong-pass-123", teacher.password_hash)


def test_students_still_cannot_use_the_staff_account_endpoints(profile_api):
    client, db, admin, _ = profile_api
    student = User(username="stu1", password_hash=hash_password("Current-pass-123"), role="user", status=ACTIVE, school_id=admin.school_id)
    db.add(student); db.commit()
    body = {"first_name": "S", "last_name": "T", "email": "s@example.com", "username": "stu_renamed"}
    assert client.put("/profile/account", headers=_login("stu1"), json=body).status_code == 403
    assert client.put("/profile/password", headers=_login("stu1"), json={"current_password": "Current-pass-123", "new_password": "New-strong-pass-123"}).status_code == 403
    db.refresh(student)
    assert student.username == "stu1"
