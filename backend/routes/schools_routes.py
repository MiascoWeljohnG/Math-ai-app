"""Schools: there are exactly two (config.SCHOOL_NAMES, created at startup by bootstrap.ensure_schools), so the only
route is the public list the sign-up form needs before anyone is logged in. No route creates or renames a school."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import School

router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("")
def list_schools(db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name} for s in db.query(School).order_by(School.name)]

