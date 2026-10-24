import re
from datetime import date
from hashlib import sha256

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

import certificates
import config
import ratelimit
from auth import DUMMY_HASH, check_password_strength, create_access_token, hash_password, verify_password
from database import get_db
from models import ACTIVE, PENDING, REJECTED, AuditLog, School, StudentCertificate, User

router = APIRouter(prefix="/auth", tags=["auth"])

STUDENT_ID_FORMAT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,39}")


class LoginRequest(BaseModel):
    username: str
    password: str


def _save_certificate(db: Session, user: User, data: bytes, content_type: str, ext: str, filename: str | None) -> str:
    """Store the file and queue its database row. Returns the storage ref so the caller can remove the file if its commit fails."""
    ref = certificates.save(data, ext)
    db.add(StudentCertificate(
        user_id=user.id, storage_ref=ref, original_name=(filename or "")[:120], content_type=content_type,
        size_bytes=len(data), sha256=sha256(data).hexdigest(),
    ))
    return ref


@router.post("/register")
async def register(
    request: Request,
    student_id: str = Form(...),
    last_name: str = Form(...),
    first_name: str = Form(...),
    middle_name: str = Form(""),
    email: str = Form(...),
    birthday: str = Form(...),            # YYYY-MM-DD
    password: str = Form(...),
    school_id: int = Form(...),           # one of the two fixed schools
    certificate: UploadFile = File(...),  # proof of enrollment (PDF / PNG / JPG)
    db: Session = Depends(get_db),
):
    """Self-service sign-up creates a PENDING student and nothing else: no token, no access, and the role is
    never taken from the request. A reviewer of the chosen school has to approve it (routes/approval_routes.py)."""
    ratelimit.limit(request, "register", max_hits=config.SIGNUP_ATTEMPTS_PER_HOUR, per_seconds=3600)

    student_id = student_id.strip()
    last_name = " ".join(last_name.split())
    first_name = " ".join(first_name.split())
    middle_name = " ".join(middle_name.split())
    email = email.strip()
    if not student_id or not last_name or not first_name:
        raise HTTPException(400, "Student ID, last name and first name are required")
    if not STUDENT_ID_FORMAT.fullmatch(student_id):
        raise HTTPException(400, "That is not a valid Student ID")
    if not re.fullmatch(r"\S+@\S+\.\S+", email):
        raise HTTPException(400, "Please enter a valid email address")
    check_password_strength(password)

    birthday = birthday.strip()
    try:
        born = date.fromisoformat(birthday)
    except ValueError:
        raise HTTPException(400, "Birthday must be a valid date (YYYY-MM-DD)")
    if born > date.today():
        raise HTTPException(400, "Birthday cannot be in the future")

    school = db.query(School).filter(School.id == school_id).first()
    if school is None:
        raise HTTPException(400, "Please choose your school")

    # The Student ID is the login username.
    if db.query(User).filter(User.username == student_id).first():
        raise HTTPException(400, "An account with this Student ID already exists")

    # Everything that can be refused is checked before the first database write.
    data = await certificates.read_upload(certificate)
    content_type, ext = certificates.sniff(data)
    user = User(
        username=student_id, student_id=student_id, first_name=first_name, last_name=last_name,
        middle_name=middle_name, email=email, birthday=birthday, password_hash=hash_password(password),
        role="user", school_id=school.id, status=PENDING, submissions=1,
    )
    ref = None
    try:
        db.add(user)
        db.flush()
        ref = _save_certificate(db, user, data, content_type, ext, certificate.filename)
        db.add(AuditLog(actor=student_id, school_id=school.id, action="student.register", target=student_id))
        db.commit()
    except Exception:
        db.rollback()   # no half-created account, and no orphaned file
        if ref:
            certificates.delete(ref)
        raise
    return {"status": PENDING, "message": f"Your registration was sent to {school.name} for approval. You can log in once it is approved."}


@router.post("/resubmit")
async def resubmit(
    request: Request,
    student_id: str = Form(...),
    password: str = Form(...),
    certificate: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """A rejected student sends a new certificate. The password proves it is their account, and the number of
    tries is capped so a student cannot keep a reviewer busy forever."""
    ratelimit.limit(request, "resubmit", max_hits=config.SIGNUP_ATTEMPTS_PER_HOUR, per_seconds=3600)
    user = db.query(User).filter(User.username == student_id.strip()).first()
    if not verify_password(password, user.password_hash if user else DUMMY_HASH) or user is None:
        raise HTTPException(401, "Invalid Student ID or password")
    if user.role != "user" or user.status != REJECTED:
        raise HTTPException(409, "Only a rejected registration can be resubmitted")
    if (user.submissions or 1) >= config.MAX_SUBMISSIONS:
        raise HTTPException(403, "You have used all your attempts. Please contact your school administrator.")

    data = await certificates.read_upload(certificate)
    content_type, ext = certificates.sniff(data)
    ref = None
    try:
        ref = _save_certificate(db, user, data, content_type, ext, certificate.filename)
        user.status, user.rejection_reason, user.submissions = PENDING, None, (user.submissions or 1) + 1
        db.add(AuditLog(actor=user.username, school_id=user.school_id, action="student.resubmit", target=user.username, detail=f"attempt={user.submissions}"))
        db.commit()
    except Exception:
        db.rollback()
        if ref:
            certificates.delete(ref)
        raise
    return {"status": PENDING, "message": "Your new certificate was sent for review."}


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    # Same work whether or not the account exists, and the same message for "no account" and "wrong password".
    password_ok = verify_password(req.password, user.password_hash if user else DUMMY_HASH)
    if not user or not password_ok:
        raise HTTPException(401, "Invalid username or password")

    # Only someone who knows the password learns the account's state.
    if user.status == PENDING:
        raise HTTPException(403, "Your account is still waiting for approval by your school administrator.")
    if user.status == REJECTED:
        why = f" Reason: {user.rejection_reason}." if user.rejection_reason else ""
        raise HTTPException(403, f"Your registration was not approved.{why} You can send a new certificate from the sign-up page.")
    if user.status != ACTIVE:
        raise HTTPException(403, "This account is not active.")

    token = create_access_token({"sub": user.username})
    school = db.query(School).filter(School.id == user.school_id).first() if user.school_id else None
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "full_name": user.display_name,        # kept so older cached pages still greet the user
        "first_name": user.first_name or user.username,
        "last_name": user.last_name,
        "middle_name": user.middle_name,
        "school_id": user.school_id,
        "school_name": school.name if school else None,
    }
