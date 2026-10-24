"""Account helpers used by the school admin routes (routes/school_admin_routes.py)."""
from datetime import date
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import check_password_strength, hash_password
from models import ACTIVE, AuditLog, School, User


class CreateTeacherRequest(BaseModel):
    username: str
    last_name: str
    first_name: str
    middle_name: str = ""   # optional
    email: str
    birthday: str = ""   # YYYY-MM-DD
    password: str
    school_id: Optional[int] = None   # ignored: a school admin only creates accounts for their own school


def school_or_400(db: Session, school_id: Optional[int]) -> School:
    """Every account and every student number belongs to one of the two fixed schools."""
    if school_id is None:
        raise HTTPException(status_code=400, detail="Choose a school")
    school = db.query(School).filter(School.id == school_id).first()
    if school is None:
        raise HTTPException(status_code=400, detail="That school does not exist")
    return school


def new_account(req: CreateTeacherRequest, role: str, school_id: int, db: Session, actor: str = "system") -> User:
    """Validate and save one teacher account. Teachers are made by a school admin (who is already trusted), so
    they start ACTIVE; only self-service student sign-ups go through approval. There is no function that makes
    admins: the two default school admins are created at startup (bootstrap.py)."""
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    check_password_strength(req.password)

    birthday = (req.birthday or "").strip()
    if not birthday:
        raise HTTPException(status_code=400, detail="Birthday is required")
    try:
        born = date.fromisoformat(birthday)
    except ValueError:
        raise HTTPException(status_code=400, detail="Birthday must be a valid date (YYYY-MM-DD)")
    if born > date.today():
        raise HTTPException(status_code=400, detail="Birthday cannot be in the future")

    last_name = " ".join((req.last_name or "").split())
    first_name = " ".join((req.first_name or "").split())
    if not last_name or not first_name:
        raise HTTPException(status_code=400, detail="Last name and first name are required")

    account = User(
        username=req.username,
        first_name=first_name,
        last_name=last_name,
        middle_name=" ".join((req.middle_name or "").split()),
        email=req.email,
        birthday=birthday,
        password_hash=hash_password(req.password),
        role=role,
        school_id=school_id,
        status=ACTIVE,
    )
    db.add(account)
    db.add(AuditLog(actor=actor, school_id=school_id, action=f"{role}.create", target=req.username))
    db.commit()
    return account
