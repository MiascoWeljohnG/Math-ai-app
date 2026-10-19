from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import RegisteredStudent, School, User
from auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    # Matches the Create Account screen: Student ID, Full name, Email, Birthday, Password.
    student_id: str
    full_name: str
    email: str
    birthday: str   # YYYY-MM-DD
    password: str
    school_id: Optional[int] = None   # required once the main admin has added any school


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    student_id = req.student_id.strip()
    full_name = " ".join(req.full_name.split())
    if not student_id or not full_name:
        raise HTTPException(400, "Student ID and full name are required")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    birthday = req.birthday.strip()
    if not birthday:
        raise HTTPException(400, "Birthday is required")
    try:
        born = date.fromisoformat(birthday)
    except ValueError:
        raise HTTPException(400, "Birthday must be a valid date (YYYY-MM-DD)")
    if born > date.today():
        raise HTTPException(400, "Birthday cannot be in the future")

    # Once the admins have registered any student numbers, only those can sign up, and the student joins
    # the school their number is listed under. Before that, students pick their school themselves.
    school_id = None
    if db.query(RegisteredStudent).count():
        registered = db.query(RegisteredStudent).filter(RegisteredStudent.student_number == student_id).first()
        if registered is None:
            raise HTTPException(400, "This Student ID is not registered. Please check it, or ask your school.")
        school_id = registered.school_id
    elif db.query(School).count():
        if req.school_id is None or not db.query(School).filter(School.id == req.school_id).first():
            raise HTTPException(400, "Please choose your school")
        school_id = req.school_id

    # The Student ID is the login username.
    if db.query(User).filter(User.username == student_id).first():
        raise HTTPException(400, "An account with this Student ID already exists")

    # Keep first/last name filled in too, so the admin and teacher tables
    # (which still read those columns) keep showing sensible names.
    parts = full_name.split(" ")
    first_name = " ".join(parts[:-1]) if len(parts) > 1 else full_name
    last_name = parts[-1] if len(parts) > 1 else ""

    user = User(
        username=student_id,
        student_id=student_id,
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        middle_name="",
        email=req.email.strip(),
        birthday=birthday,
        password_hash=hash_password(req.password),
        role="user",
        school_id=school_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User created. You can now log in."}


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")

    token = create_access_token({"sub": user.username})
    display_name = user.full_name or " ".join(filter(None, [user.first_name, user.last_name])) or user.username
    school = db.query(School).filter(School.id == user.school_id).first() if user.school_id else None
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "full_name": display_name,
        "school_id": user.school_id,
        "school_name": school.name if school else None,   # None = the main pool
    }
