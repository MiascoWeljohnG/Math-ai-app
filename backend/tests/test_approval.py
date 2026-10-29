"""Pending-approval sign-up: certificate upload, reviewer scoping, login gating, resubmission, bootstrap.
Unlike the other route tests these use REAL tokens (no get_current_user override), because the point is that
the authentication gate itself refuses accounts that are not active."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
import ratelimit
from auth import hash_password
from bootstrap import ensure_school_admins, ensure_schools, retire_main_admins
from database import get_db
from models import AuditLog, PasswordResetToken, School, StudentCertificate, User
from routes import approval_routes, auth_routes, school_admin_routes, schools_routes

PDF = b"%PDF-1.4\n% enrollment certificate\n" + b"x" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 200
PASSWORD = "Sup3rsecret"


@pytest.fixture
def api(db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CERT_DIR", str(tmp_path / "certs"))
    monkeypatch.setattr(config, "SIGNUP_ATTEMPTS_PER_HOUR", 1000)   # the rate-limit test lowers this
    ratelimit.reset()
    app = FastAPI()
    for module in (auth_routes, approval_routes, school_admin_routes, schools_routes):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: db
    ensure_schools(db)
    schools = {s.name: s for s in db.query(School)}
    for username, role, school in (("adm_a", "school_admin", "School A"), ("adm_b", "school_admin", "School B"), ("teach_a", "teacher", "School A")):
        db.add(User(username=username, password_hash=hash_password(PASSWORD), role=role, status="active", school_id=schools[school].id))
    db.commit()
    return SimpleNamespace(client=TestClient(app), db=db, a=schools["School A"], b=schools["School B"], tmp=tmp_path)


def form(api, student_id="2024-1", **over):
    data = {"student_id": student_id, "last_name": "Cruz", "first_name": "Ana", "middle_name": "", "email": "ana@school.ph",
            "birthday": "2005-03-08", "password": PASSWORD, "school_id": str(api.a.id)}
    data.update(over)
    return data


def sign_up(api, student_id="2024-1", file=("cor.pdf", PDF, "application/pdf"), **over):
    return api.client.post("/auth/register", data=form(api, student_id, **over), files={"certificate": file})


def login(api, username, password=PASSWORD):
    return api.client.post("/auth/login", json={"username": username, "password": password})


def test_password_recovery_creates_single_use_email_token_and_resets_password(api, db, monkeypatch):
    from routes import auth_routes
    sent = []
    monkeypatch.setattr(auth_routes, "send_password_reset_email", lambda email, link: sent.append((email, link)))
    db.add(User(username="recover-me", email="recover@example.com", password_hash=hash_password(PASSWORD), role="user", status="active", school_id=api.a.id))
    db.commit()

    requested = api.client.post("/auth/forgot-password", json={"username": "recover-me"})
    assert requested.status_code == 200 and sent[0][0] == "recover@example.com"
    token = sent[0][1].split("token=", 1)[1]
    changed = api.client.post("/auth/reset-password", json={"token": token, "password": "New-password-123"})
    assert changed.status_code == 200
    account = db.query(User).filter(User.username == "recover-me").first()
    assert account.password_hash != hash_password(PASSWORD)
    from auth import verify_password
    assert verify_password("New-password-123", account.password_hash)
    assert db.query(PasswordResetToken).filter(PasswordResetToken.used_at.is_(None)).count() == 0


def headers(api, username):
    res = login(api, username)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ---------------------------------------------------------------- sign-up creates a pending account
def test_sign_up_creates_a_pending_student_who_cannot_log_in(api):
    res = sign_up(api)
    assert res.status_code == 200 and res.json()["status"] == "pending" and "access_token" not in res.json()
    student = api.db.query(User).filter(User.username == "2024-1").one()
    assert (student.role, student.status, student.school_id) == ("user", "pending", api.a.id)
    assert api.db.query(StudentCertificate).filter(StudentCertificate.user_id == student.id).count() == 1

    pending = login(api, "2024-1")
    assert pending.status_code == 403 and "waiting for approval" in pending.json()["detail"]
    # the account's state is only revealed to someone who knows the password; everyone else gets the same answer
    wrong, unknown = login(api, "2024-1", "wrong-password"), login(api, "nobody")
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()


def test_sign_up_cannot_choose_a_role_a_school_outside_the_two_or_skip_the_certificate(api):
    res = sign_up(api, "2024-2", role="school_admin", status="active")   # extra fields are ignored
    assert res.status_code == 200
    row = api.db.query(User).filter(User.username == "2024-2").one()
    assert (row.role, row.status) == ("user", "pending")

    assert sign_up(api, "2024-3", school_id="999").status_code == 400
    assert sign_up(api, "2024-3", school_id="").status_code == 422
    assert sign_up(api, "2024-3", password="short").status_code == 400
    assert sign_up(api, "2024-3", email="not-an-email").status_code == 400
    assert sign_up(api, "bad id!").status_code == 400
    assert api.client.post("/auth/register", data=form(api, "2024-3")).status_code == 422   # no certificate at all
    assert sign_up(api, "2024-2").status_code == 400                                          # Student ID already used
    assert api.db.query(User).filter(User.username == "2024-3").first() is None


def test_certificate_must_really_be_a_pdf_png_or_jpg_of_reasonable_size(api, monkeypatch):
    assert sign_up(api, "e1", file=("cor.pdf", b"MZ\x90\x00 this is an exe", "application/pdf")).status_code == 400   # name and type lie
    assert sign_up(api, "e2", file=("cor.pdf", b"<html><script>alert(1)</script>", "application/pdf")).status_code == 400
    assert sign_up(api, "e3", file=("cor.pdf", b"", "application/pdf")).status_code == 400
    assert sign_up(api, "ok", file=("anything.bin", PNG, "application/octet-stream")).status_code == 200   # judged by its bytes
    assert api.db.query(StudentCertificate).one().content_type == "image/png"
    monkeypatch.setattr(config, "CERT_MAX_BYTES", 100)
    assert sign_up(api, "big", file=("cor.pdf", PDF, "application/pdf")).status_code == 413
    # a refused sign-up leaves no account and no stray file behind
    assert api.db.query(User).filter(User.username.in_(["e1", "e2", "e3", "big"])).count() == 0
    assert len(list((api.tmp / "certs").iterdir())) == 1


def test_sign_up_is_rate_limited(api, monkeypatch):
    monkeypatch.setattr(config, "SIGNUP_ATTEMPTS_PER_HOUR", 5)
    codes = [sign_up(api, f"r{i}", password="short").status_code for i in range(6)]
    assert codes == [400] * 5 + [429]


# ---------------------------------------------------------------- reviewers
def test_school_admin_approves_and_the_student_can_log_in(api):
    sign_up(api)
    reviewer = headers(api, "adm_a")
    queue = api.client.get("/approvals/pending", headers=reviewer).json()
    assert [(q["username"], q["school"], q["attempt"]) for q in queue] == [("2024-1", "School A", 1)]
    assert queue[0]["certificate"] == {"type": "application/pdf", "size": len(PDF)}
    assert "storage_ref" not in str(queue)   # where the file lives is never sent to the browser

    seen = api.client.get("/approvals/2024-1/certificate", headers=reviewer)
    assert seen.status_code == 200 and seen.content == PDF and seen.headers["content-type"] == "application/pdf"
    assert seen.headers["x-content-type-options"] == "nosniff" and "sandbox" in seen.headers["content-security-policy"]

    assert api.client.post("/approvals/2024-1/approve", headers=reviewer).status_code == 200
    assert api.client.get("/approvals/pending", headers=reviewer).json() == []
    ok = login(api, "2024-1")
    assert ok.status_code == 200 and ok.json()["role"] == "user" and ok.json()["school_name"] == "School A"
    row = api.db.query(User).filter(User.username == "2024-1").one()
    assert (row.status, row.reviewed_by) == ("active", "adm_a")
    log = [(r.actor, r.action, r.target) for r in api.db.query(AuditLog).order_by(AuditLog.id)]
    assert ("adm_a", "student.approve", "2024-1") in log and ("adm_a", "certificate.view", "2024-1") in log


def test_reviewers_only_reach_their_own_schools_students(api):
    sign_up(api, "a-1")
    sign_up(api, "b-1", school_id=str(api.b.id))
    mine = {"a": headers(api, "adm_a"), "b": headers(api, "adm_b")}
    assert [q["username"] for q in api.client.get("/approvals/pending", headers=mine["a"]).json()] == ["a-1"]
    assert [q["username"] for q in api.client.get("/approvals/pending", headers=mine["b"]).json()] == ["b-1"]

    for action in ("certificate", "approve"):   # another school's student looks like they do not exist
        method = api.client.get if action == "certificate" else api.client.post
        assert method(f"/approvals/a-1/{action}", headers=mine["b"]).status_code == 404
    assert api.client.post("/approvals/a-1/reject", json={"reason": "not my student"}, headers=mine["b"]).status_code == 404
    assert api.db.query(User).filter(User.username == "a-1").one().status == "pending"
    assert api.client.post("/approvals/a-1/approve", headers=mine["a"]).status_code == 200   # their own school's admin can


def test_only_reviewers_can_use_the_queue_and_a_pending_students_token_is_useless(api):
    sign_up(api)
    assert api.client.get("/approvals/pending").status_code == 401   # no token
    assert api.client.get("/approvals/pending", headers=headers(api, "teach_a")).status_code == 403   # a teacher is not a reviewer

    # a token issued while the account was active stops working once it is not (checked on every request)
    api.client.post("/approvals/2024-1/approve", headers=headers(api, "adm_a"))
    student = headers(api, "2024-1")
    assert api.client.get("/approvals/pending", headers=student).status_code == 403   # a student is not a reviewer
    api.db.query(User).filter(User.username == "2024-1").update({"status": "rejected"})
    api.db.commit()
    again = api.client.get("/approvals/pending", headers=student)
    assert again.status_code == 403 and "not approved" in again.json()["detail"]


def test_a_decision_is_final_and_a_reason_is_required_to_reject(api):
    sign_up(api)
    reviewer = headers(api, "adm_a")
    assert api.client.post("/approvals/2024-1/reject", json={}, headers=reviewer).status_code == 422
    assert api.client.post("/approvals/2024-1/reject", json={"reason": "  "}, headers=reviewer).status_code == 422
    assert api.client.post("/approvals/2024-1/approve", headers=reviewer).status_code == 200
    assert api.client.post("/approvals/2024-1/approve", headers=reviewer).status_code == 409   # already decided
    assert api.client.post("/approvals/2024-1/reject", json={"reason": "too late"}, headers=reviewer).status_code == 409
    assert api.db.query(User).filter(User.username == "2024-1").one().status == "active"


def test_reviewer_is_told_when_a_certificate_file_was_used_by_another_account(api):
    for sid in ("same-1", "same-2"):
        sign_up(api, sid)   # the same file each time
    sign_up(api, "unique-1", file=("c.png", PNG, "image/png"))
    queue = {q["username"]: q for q in api.client.get("/approvals/pending", headers=headers(api, "adm_a")).json()}
    assert queue["same-1"]["certificate_reused"] and queue["same-2"]["certificate_reused"]
    assert queue["unique-1"]["certificate_reused"] is False
    assert "roster" not in queue["same-1"]   # there is no registered-students list any more


# ---------------------------------------------------------------- rejection and resubmission
def test_rejected_student_sees_the_reason_and_can_resubmit_a_limited_number_of_times(api):
    sign_up(api)
    reviewer = headers(api, "adm_a")
    api.client.post("/approvals/2024-1/reject", json={"reason": "Certificate is unreadable"}, headers=reviewer)
    res = login(api, "2024-1")
    assert res.status_code == 403 and "Certificate is unreadable" in res.json()["detail"]

    def resubmit(password=PASSWORD, file=("new.png", PNG, "image/png"), student="2024-1"):
        return api.client.post("/auth/resubmit", data={"student_id": student, "password": password}, files={"certificate": file})

    assert resubmit(password="wrong").status_code == 401
    assert resubmit(student="nobody").status_code == 401
    assert resubmit().status_code == 200
    row = api.db.query(User).filter(User.username == "2024-1").one()
    assert (row.status, row.rejection_reason, row.submissions) == ("pending", None, 2)
    queue = api.client.get("/approvals/pending", headers=reviewer).json()
    assert queue[0]["attempt"] == 2 and queue[0]["certificate"]["type"] == "image/png"   # the reviewer sees the newest file
    assert resubmit().status_code == 409   # nothing to resubmit while it is pending

    api.client.post("/approvals/2024-1/reject", json={"reason": "Still wrong"}, headers=reviewer)
    assert resubmit().status_code == 200   # attempt 3
    api.client.post("/approvals/2024-1/reject", json={"reason": "Not valid"}, headers=reviewer)
    assert resubmit().status_code == 403   # out of attempts: talk to the school
    assert api.db.query(StudentCertificate).count() == 3


# ---------------------------------------------------------------- the audit log is per school
def test_school_admin_reads_only_their_own_schools_audit_log(api):
    sign_up(api, "a-1")
    sign_up(api, "b-1", school_id=str(api.b.id))
    a, b = headers(api, "adm_a"), headers(api, "adm_b")
    api.client.get("/approvals/a-1/certificate", headers=a)
    api.client.post("/approvals/a-1/approve", headers=a)
    api.client.post("/school-admin/create-teacher", headers=a, json={
        "username": "new_t", "last_name": "L", "first_name": "F", "email": "x@y.co", "birthday": "1990-01-01", "password": "Another-pw-1"})

    mine = api.client.get("/school-admin/audit-log", headers=a).json()
    assert [(r["actor"], r["action"], r["target"]) for r in reversed(mine)] == [
        ("a-1", "student.register", "a-1"), ("adm_a", "certificate.view", "a-1"),
        ("adm_a", "student.approve", "a-1"), ("adm_a", "teacher.create", "new_t")]
    assert all({"at", "actor", "action", "target", "detail"} == set(r) for r in mine)

    theirs = api.client.get("/school-admin/audit-log", headers=b).json()   # School B sees only its own event
    assert [(r["actor"], r["action"]) for r in theirs] == [("b-1", "student.register")]

    assert api.client.get("/school-admin/audit-log").status_code == 401
    assert api.client.get("/school-admin/audit-log", headers=headers(api, "teach_a")).status_code == 403
    api.client.post("/approvals/a-1/approve", headers=a)   # (already decided) - a student is not allowed either
    assert api.client.get("/school-admin/audit-log", headers=headers(api, "a-1")).status_code == 403
    assert api.client.get("/school-admin/audit-log?limit=1", headers=a).status_code == 200 and len(api.client.get("/school-admin/audit-log?limit=1", headers=a).json()) == 1


# ---------------------------------------------------------------- default admins and the retired main admin
def test_each_school_gets_one_default_admin_from_its_settings(api, monkeypatch):
    api.db.query(User).delete()
    api.db.commit()
    monkeypatch.setattr(config, "SCHOOL_ADMIN_DEFAULTS", [("a_admin", ""), ("b_admin", "")])
    ensure_school_admins(api.db)
    assert api.db.query(User).count() == 0   # no password configured, so nothing is invented

    monkeypatch.setattr(config, "SCHOOL_ADMIN_DEFAULTS", [("a_admin", "short"), ("b_admin", "b-long-enough-password")])
    with pytest.raises(RuntimeError):
        ensure_school_admins(api.db)

    monkeypatch.setattr(config, "SCHOOL_ADMIN_DEFAULTS", [("a_admin", "a-long-enough-password"), ("b_admin", "b-long-enough-password")])
    ensure_school_admins(api.db)
    ensure_school_admins(api.db)   # idempotent
    admins = {u.username: u for u in api.db.query(User)}
    assert set(admins) == {"a_admin", "b_admin"}
    assert (admins["a_admin"].role, admins["a_admin"].school_id, admins["a_admin"].status) == ("school_admin", api.a.id, "active")
    assert admins["b_admin"].school_id == api.b.id
    assert login(api, "a_admin", "a-long-enough-password").status_code == 200
    assert login(api, "a_admin", "admin123").status_code == 401   # no built-in password


def test_a_school_that_already_has_an_admin_is_left_alone(api, monkeypatch):
    monkeypatch.setattr(config, "SCHOOL_ADMIN_DEFAULTS", [("new_a", "a-long-enough-password"), ("new_b", "b-long-enough-password")])
    ensure_school_admins(api.db)   # adm_a and adm_b already exist, so no duplicates appear
    assert {u.username for u in api.db.query(User).filter(User.role == "school_admin")} == {"adm_a", "adm_b"}


def test_old_main_and_super_admin_accounts_are_retired(api):
    api.db.add(User(username="admin", password_hash=hash_password("Old-admin-pass1"), role="admin", status="active"))
    api.db.commit()
    token = login(api, "admin", "Old-admin-pass1").json()["access_token"]
    retire_main_admins(api.db)
    assert api.db.query(User).filter(User.username == "admin").one().status == "disabled"   # kept, not deleted
    gone = login(api, "admin", "Old-admin-pass1")
    assert gone.status_code == 403 and "not active" in gone.json()["detail"]
    assert api.client.get("/approvals/pending", headers={"Authorization": f"Bearer {token}"}).status_code == 403   # an old token dies too
    retire_main_admins(api.db)   # idempotent
