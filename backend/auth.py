from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import config
from database import get_db
from models import ACTIVE, PENDING, REJECTED, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# Checked against when a login names an unknown account, so "no such user" takes as long as "wrong password".
DUMMY_HASH = pwd_context.hash("not-a-real-password")

def check_password_strength(password: str, minimum: int = config.MIN_PASSWORD_LENGTH) -> None:
    if len(password or "") < minimum:
        raise HTTPException(status_code=400, detail=f"Password must be at least {minimum} characters")

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    # The one place every protected route passes through. Checking here (not only at login) means a token
    # issued earlier stops working the moment an account is no longer active.
    if user.status != ACTIVE:
        detail = {PENDING: "Your account is waiting for approval.", REJECTED: "Your registration was not approved."}
        raise HTTPException(status_code=403, detail=detail.get(user.status, "This account is not active."))
    return user

# Roles are user (student), teacher and school_admin. A school admin is the highest role and only ever works
# inside their own school; there is no account that spans schools and no way to create admins.
def require_school_admin(user: User = Depends(get_current_user)) -> User:
    # Approves students, manages the school's teachers, files and subject deletions, and reads its audit log.
    if user.role != "school_admin" or user.school_id is None:
        raise HTTPException(status_code=403, detail="School admin access required")
    return user

def require_teacher(user: User = Depends(get_current_user)) -> User:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access required")
    return user

def require_staff(user: User = Depends(get_current_user)) -> User:
    # Teachers manage their content day-to-day; the school admin can step in for anything in their school.
    if user.role == "teacher" or (user.role == "school_admin" and user.school_id is not None):
        return user
    raise HTTPException(status_code=403, detail="Teacher or school admin access required")