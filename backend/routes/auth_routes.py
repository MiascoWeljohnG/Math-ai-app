from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User
from auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    first_name: str
    last_name: str
    middle_name: str = ""
    email: str
    birthday: str
    password: str

@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(400, "Username already exists")

    user = User(
        username=req.username,
        first_name=req.first_name,
        last_name=req.last_name,
        middle_name=req.middle_name,
        email=req.email,
        birthday=req.birthday,
        password_hash=hash_password(req.password),
        role="user",
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
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
    }   