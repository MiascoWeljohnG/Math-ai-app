"""The school admin's own page: everything here is limited to the admin's school, and the school comes
from their account (never from the request), so it cannot be switched by editing the page."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import config
import drive_storage
from accounts import CreateTeacherRequest, new_account
from auth import require_school_admin
from database import get_db
from models import AuditLog, Material, User
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
            "middle_name": u.middle_name,
            "email": u.email,
            "birthday": u.birthday,
            "role": u.role,
            "status": u.status,
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
    new_account(req, "teacher", user.school_id, db, actor=user.username)   # req.school_id is ignored on purpose
    return {"message": f"Teacher account '{req.username}' created."}


@router.get("/files")
def school_files(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """The files this school's teachers uploaded."""
    names = {u.username: u.person_name for u in db.query(User).filter(User.school_id == user.school_id)}
    rows = (
        db.query(Material)
        .filter(Material.school_id == user.school_id)
        .order_by(Material.uploaded_at.desc(), Material.id.desc())
        .all()
    )
    return [{**material_summary(m), "uploaded_by_name": names.get(m.uploaded_by, "")} for m in rows]


@router.delete("/files/{filename:path}")
def delete_school_file(filename: str, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """Delete one of this school's files: its record, the original on disk or Drive, and the AI's chunks from it."""
    from rag import delete_material_chunks
    material = db.query(Material).filter(Material.filename == filename, Material.school_id == user.school_id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="File not found")

    if material.drive_file_id:
        try:   # first, so a Drive failure leaves everything as it was and the delete can simply be retried
            drive_storage.delete_file(material.drive_file_id)
        except drive_storage.DriveStorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    delete_material_chunks(material.filename)
    vault_dir = Path(config.CHROMA_VAULT_DIR).expanduser().resolve()
    target = (vault_dir / material.filename).resolve()
    if vault_dir in target.parents and target.is_file():   # never delete outside the uploads folder
        target.unlink()

    name = material.display_name
    db.delete(material)
    db.add(AuditLog(actor=user.username, school_id=user.school_id, action="file.delete", target=name))
    db.commit()
    return {"message": f'Deleted "{name}".'}


@router.get("/audit-log")
def school_audit_log(limit: int = 200, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """What happened in this school: sign-ups, approvals and rejections, certificate views, accounts created,
    files and subjects deleted. The school comes from the signed-in account, so another school's events are unreachable."""
    rows = (
        db.query(AuditLog).filter(AuditLog.school_id == user.school_id)
        .order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500))).all()
    )
    return [{"at": r.created_at.isoformat() + "Z", "actor": r.actor, "action": r.action, "target": r.target, "detail": r.detail} for r in rows]
