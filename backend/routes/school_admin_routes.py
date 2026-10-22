"""The school admin's own page: everything here is limited to the admin's school, and the school comes
from their account (never from the request), so it cannot be switched by editing the page."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import require_school_admin
from database import get_db
from models import Material, RegisteredStudent, User
from routes.admin_routes import (
    CreateTeacherRequest, RegisteredNumbersRequest, add_registered, new_account, registry_items, remove_registered,
)
from routes.materials_routes import material_summary

router = APIRouter(prefix="/school-admin", tags=["school-admin"])


@router.get("/users")
def school_users(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    rows = db.query(User).filter(User.school_id == user.school_id).order_by(User.role, User.username).all()
    return [
        {
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "full_name": u.full_name,
            "email": u.email,
            "birthday": u.birthday,
            "role": u.role,
            "created": str(u.created_at),
        }
        for u in rows
    ]


@router.post("/create-teacher")
def create_school_teacher(
    req: CreateTeacherRequest,
    user: User = Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    new_account(req, "teacher", user.school_id, db)   # req.school_id is ignored on purpose
    return {"message": f"Teacher account '{req.username}' created."}


@router.get("/files")
def school_files(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """The files this school's teachers uploaded."""
    names = {u.username: " ".join(filter(None, [u.first_name, u.last_name])) for u in db.query(User).filter(User.school_id == user.school_id)}
    rows = (
        db.query(Material)
        .filter(Material.school_id == user.school_id)
        .order_by(Material.uploaded_at.desc(), Material.id.desc())
        .all()
    )
    return [{**material_summary(m), "uploaded_by_name": names.get(m.uploaded_by, "")} for m in rows]


@router.post("/registered-students")
def add_school_students(req: RegisteredNumbersRequest, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    return add_registered(db, req.numbers, user.school_id)   # req.school_id is ignored on purpose


@router.get("/registered-students")
def list_school_students(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    rows = db.query(RegisteredStudent).filter(RegisteredStudent.school_id == user.school_id).order_by(RegisteredStudent.id.desc()).all()
    return registry_items(db, rows)


@router.delete("/registered-students/{row_id}")
def delete_school_student(row_id: int, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    row = db.query(RegisteredStudent).filter(RegisteredStudent.id == row_id, RegisteredStudent.school_id == user.school_id).first()
    return remove_registered(db, row)
