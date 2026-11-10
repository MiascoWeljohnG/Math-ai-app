"""One device at a time: a new login ends the session on the device that was signed in before."""
from datetime import date, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
import ratelimit
from auth import SESSION_REPLACED, create_access_token, hash_password
from database import get_db
from models import PasswordResetToken, School, User
from routes import auth_routes, teacher_routes

PASSWORD = "Password-123"


@pytest.fixture
def api(db, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_NAMES", ("School A", "School B"))
    monkeypatch.setattr(config, "SINGLE_DEVICE_LOGIN", True)
    ratelimit.reset()
    app = FastAPI()
    for module in (auth_routes, teacher_routes):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: db
    school = School(name="School A")
    db.add(school)
    db.flush()
    db.add(User(username="tea1", password_hash=hash_password(PASSWORD), role="teacher", status="active",
                school_id=school.id, created_at=date.today()))
    db.commit()
    return TestClient(app), db


def login(client, username="tea1", password=PASSWORD):
    return client.post("/auth/login", json={"username": username, "password": password})


def bearer(res):
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def ping(client, headers):
    """Any protected route will do."""
    return client.get("/teacher/subjects", headers=headers)


def test_logging_in_on_a_second_device_signs_the_first_one_out(api):
    client, _ = api
    laptop, phone = bearer(login(client)), bearer(login(client))
    assert ping(client, phone).status_code == 200
    old = ping(client, laptop)
    assert old.status_code == 401
    assert old.json()["detail"] == SESSION_REPLACED
    assert "another device" in old.json()["detail"]   # the pages look for these words (frontend/js/auth.js)


def test_the_newest_login_keeps_working_across_many_requests(api):
    client, _ = api
    login(client)
    phone = bearer(login(client))
    assert all(ping(client, phone).status_code == 200 for _ in range(3))


def test_a_failed_login_does_not_sign_out_the_device_that_is_in(api):
    client, _ = api
    laptop = bearer(login(client))
    assert login(client, password="wrong-password").status_code == 401
    assert ping(client, laptop).status_code == 200


def test_a_token_from_before_this_rule_works_until_the_next_login(api):
    client, _ = api
    legacy = {"Authorization": f"Bearer {create_access_token({'sub': 'tea1'})}"}   # no session id, as every old token
    assert ping(client, legacy).status_code == 200
    login(client)
    assert ping(client, legacy).status_code == 401


def test_the_rule_can_be_switched_off(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(config, "SINGLE_DEVICE_LOGIN", False)
    laptop, phone = bearer(login(client)), bearer(login(client))
    assert ping(client, laptop).status_code == 200
    assert ping(client, phone).status_code == 200


def test_a_password_reset_signs_every_device_out(api):
    client, db = api
    laptop = bearer(login(client))
    user = db.query(User).filter(User.username == "tea1").first()
    db.add(PasswordResetToken(user_id=user.id, token_hash=sha256(b"raw-token").hexdigest(),
                              expires_at=datetime.utcnow() + timedelta(minutes=10)))
    db.commit()
    assert client.post("/auth/reset-password", json={"token": "raw-token", "password": "A-brand-new-pass"}).status_code == 200
    assert ping(client, laptop).status_code == 401
    assert ping(client, bearer(login(client, password="A-brand-new-pass"))).status_code == 200
