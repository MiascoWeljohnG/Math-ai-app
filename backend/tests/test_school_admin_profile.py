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
