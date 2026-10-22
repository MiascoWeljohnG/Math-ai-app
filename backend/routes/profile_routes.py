from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User

router = APIRouter(tags=["profile"])

# The photo is stored as a small data-URL (the browser shrinks it first), so
# no file-upload plumbing is needed. Hard cap keeps the DB row sane.
MAX_AVATAR_CHARS = 400_000


class ProfileUpdate(BaseModel):
    full_name: str
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


def _display_name(u: User) -> str:
    return u.full_name or " ".join(filter(None, [u.first_name, u.last_name])) or u.username


def _serialize(u: User) -> dict:
    return {
        "username": u.username,
        "role": u.role,
        "full_name": _display_name(u),
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


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user)):
    return _serialize(user)


@router.put("/profile")
def update_profile(
    req: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    full_name = " ".join(req.full_name.split())
    if not full_name:
        raise HTTPException(400, "Full name is required")

    user.full_name = full_name
    parts = full_name.split(" ")
    user.first_name = " ".join(parts[:-1]) if len(parts) > 1 else full_name
    user.last_name = parts[-1] if len(parts) > 1 else ""

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
