"""Schools: the main admin adds them, anyone can list them (the sign-up form needs the names before login)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import RegisteredStudent, School, Subject
from progress import BRANCHES

router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("")
def list_schools(db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name} for s in db.query(School).order_by(School.name)]


@router.get("/signup-mode")
def signup_mode(db: Session = Depends(get_db)):
    """True once any student number is registered: sign-up then needs a registered number and the
    school comes from the list, so the page hides its school dropdown."""
    return {"registry": db.query(RegisteredStudent).count() > 0}


class SchoolRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.post("")
def create_school(req: SchoolRequest, user=Depends(require_admin), db: Session = Depends(get_db)):
    name = " ".join(req.name.split())
    if not name:
        raise HTTPException(status_code=400, detail="School name is required")
    if db.query(School).filter(func.lower(School.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail=f'A school called "{name}" already exists')
    school = School(name=name)
    db.add(school)
    db.flush()
    # Same four starting subjects main.py seeds, so a new school is usable on day one (they start empty).
    db.add_all(Subject(name=branch, school_id=school.id) for branch in BRANCHES)
    db.commit()
    return {"id": school.id, "name": school.name}
