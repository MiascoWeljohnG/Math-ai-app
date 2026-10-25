from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import check_password_strength, get_current_user, hash_password, verify_password
from database import get_db
from models import User

router = APIRouter(tags=["profile"])

# The photo is stored as a small data-URL (the browser shrinks it first), so
# no file-upload plumbing is needed. Hard cap keeps the DB row sane.
MAX_AVATAR_CHARS = 400_000


class ProfileUpdate(BaseModel):
    last_name: str
    first_name: str
    middle_name: Optional[str] = ""
    email: str
    contact_number: Optional[str] = ""
    birthday: Optional[str] = ""
    gender: Optional[str] = ""
    address: Optional[str] = ""
    student_id: Optional[str] = ""
    grade_section: Optional[str] = ""
    strand: Optional[str] = ""
    school_year: Optional[str] = ""
    avatar: Optional[str] = None  # None = leave unchanged, "" = remove


class SchoolAdminAccountUpdate(BaseModel):
    first_name: str
    last_name: str
    middle_name: Optional[str] = ""
    email: str
    username: str


class SchoolAdminPasswordUpdate(BaseModel):
    current_password: str
    new_password: str


def _display_name(u: User) -> str:
    return u.display_name


def _serialize(u: User) -> dict:
    return {
        "username": u.username,
        "role": u.role,
        "last_name": u.last_name or "",
        "first_name": u.first_name or "",
        "middle_name": u.middle_name or "",
        "display_name": _display_name(u),
        "email": u.email or "",
        "contact_number": u.contact_number or "",
        "birthday": u.birthday or "",
        "gender": u.gender or "",
        "address": u.address or "",
        "student_id": u.student_id or "",
        "grade_section": u.grade_section or "",
        "strand": u.strand or "",
        "school_year": u.school_year or "",
        "avatar": u.avatar or "",
    }


@router.put("/profile/account")
def update_school_admin_account(
    req: SchoolAdminAccountUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "school_admin" or user.school_id is None:
        raise HTTPException(403, "School admin access required")
    first_name = " ".join(req.first_name.split())
    last_name = " ".join(req.last_name.split())
    middle_name = " ".join((req.middle_name or "").split())
    username = req.username.strip()
    email = req.email.strip()
    if not first_name or not last_name or not username:
        raise HTTPException(400, "First name, last name and username are required")
    if len(username) > 80 or any(ch.isspace() for ch in username):
        raise HTTPException(400, "Username must be 1–80 characters with no spaces")
    if email and (len(email) > 254 or "@" not in email or email.startswith("@") or email.endswith("@")):
        raise HTTPException(400, "Enter a valid email address")
    collision = db.query(User).filter(User.username == username, User.id != user.id).first()
    if collision:
        raise HTTPException(409, "That username is already in use")
    user.first_name, user.last_name, user.middle_name = first_name, last_name, middle_name
    user.email, user.username = email, username
    db.commit()
    db.refresh(user)
    return {"username": user.username, "first_name": user.first_name, "last_name": user.last_name,
            "middle_name": user.middle_name or "", "email": user.email or "", "display_name": user.display_name}


@router.put("/profile/password")
def update_school_admin_password(
    req: SchoolAdminPasswordUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "school_admin" or user.school_id is None:
        raise HTTPException(403, "School admin access required")
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    check_password_strength(req.new_password)
    if verify_password(req.new_password, user.password_hash):
        raise HTTPException(400, "Choose a password you haven't used before")
    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "Password updated"}


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user)):
    return _serialize(user)


@router.put("/profile")
def update_profile(
    req: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    last_name = " ".join(req.last_name.split())
    first_name = " ".join(req.first_name.split())
    if not last_name or not first_name:
        raise HTTPException(400, "Last name and first name are required")

    user.last_name = last_name
    user.first_name = first_name
    user.middle_name = " ".join((req.middle_name or "").split())

    user.email = req.email.strip()
    user.contact_number = (req.contact_number or "").strip()
    user.birthday = (req.birthday or "").strip()
    user.gender = (req.gender or "").strip()
    user.address = (req.address or "").strip()
    user.grade_section = (req.grade_section or "").strip()
    user.strand = (req.strand or "").strip()
    user.school_year = (req.school_year or "").strip()

    # Student ID doubles as the login username for new accounts, so it isn't
    # editable here — it's shown read-only. Older accounts without one can
    # set it once.
    if not user.student_id and req.student_id:
        user.student_id = req.student_id.strip()

    if req.avatar is not None:
        if req.avatar and not req.avatar.startswith("data:image/"):
            raise HTTPException(400, "Invalid image")
        if len(req.avatar) > MAX_AVATAR_CHARS:
            raise HTTPException(400, "Image is too large")
        user.avatar = req.avatar

    db.commit()
    db.refresh(user)
    return _serialize(user)
