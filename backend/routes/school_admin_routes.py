"""The school admin's own page: everything here is limited to the admin's school, and the school comes
from their account (never from the request), so it cannot be switched by editing the page."""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import config
import drive_storage
from accounts import CreateTeacherRequest, new_account
from auth import require_school_admin
from database import get_db
from audit import SECTIONS, log_view
from models import ACTIVE, DISABLED, PENDING, AuditLog, FileDeletionRequest, Material, Subject, SubjectDeletionRequest, User
from routes.materials_routes import material_summary
from routes.subject_deletion_routes import OPEN as OPEN_DELETION_STATUSES
from school import in_school, shared_subjects

router = APIRouter(prefix="/school-admin", tags=["school-admin"])


@router.get("/users")
def school_users(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    rows = db.query(User).filter(User.school_id == user.school_id).order_by(User.role, User.username).all()
    result = [
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
    log_view(db, user, "users.view", detail=f"{len(result)} accounts")   # emails and birthdays: record who looked
    return result


# An account counts as "online now" if it made a request in this long (see auth._touch_last_seen).
ONLINE_WINDOW = timedelta(minutes=15)


@router.get("/overview")
def school_overview(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """The four numbers at the top of the school admin page. Everything is counted for the admin's own school
    only (the school comes from the account, never from the request)."""
    now = datetime.utcnow()
    in_my_school = in_school(User.school_id, user.school_id)

    # Accounts: how many can sign in, out of every account the school has (retired ones are not counted).
    total_accounts = db.query(func.count(User.id)).filter(in_my_school, User.status != DISABLED).scalar() or 0
    active_by_role = dict(
        db.query(User.role, func.count(User.id)).filter(in_my_school, User.status == ACTIVE).group_by(User.role).all()
    )
    active_accounts = sum(active_by_role.values())

    # Files: what the school's teachers and admin have uploaded to the knowledge base.
    in_my_files = in_school(Material.school_id, user.school_id)
    total_files = db.query(func.count(Material.id)).filter(in_my_files).scalar() or 0
    files_this_week = db.query(func.count(Material.id)).filter(in_my_files, Material.uploaded_at >= now - timedelta(days=7)).scalar() or 0
    latest_upload = db.query(func.max(Material.uploaded_at)).filter(in_my_files).scalar()

    # People using the system: active accounts that made a request recently.
    seen_since = lambda delta: db.query(User.role, func.count(User.id)).filter(
        in_my_school, User.status == ACTIVE, User.last_seen_at >= now - delta).group_by(User.role).all()
    online_by_role = dict(seen_since(ONLINE_WINDOW))
    seen_today = sum(dict(seen_since(timedelta(hours=24))).values())

    # What needs the admin: students waiting for approval and subject deletions waiting for a decision.
    waiting = db.query(func.count(User.id), func.min(User.created_at)).filter(in_my_school, User.role == "user", User.status == PENDING).one()
    pending_approvals, oldest_waiting = waiting[0] or 0, waiting[1]
    pending_deletions = (
        db.query(func.count(SubjectDeletionRequest.id))
        .join(Subject, Subject.id == SubjectDeletionRequest.subject_id)
        .filter(SubjectDeletionRequest.status.in_(OPEN_DELETION_STATUSES), shared_subjects(user))
        .scalar() or 0
    )
    pending_deletions += (
        db.query(func.count(FileDeletionRequest.id))
        .filter(FileDeletionRequest.status == "pending", FileDeletionRequest.school_id == user.school_id)
        .scalar() or 0
    )

    return {
        "accounts": {
            "active": active_accounts,
            "total": total_accounts,
            "students": active_by_role.get("user", 0),
            "teachers": active_by_role.get("teacher", 0),
            "admins": active_by_role.get("school_admin", 0),
        },
        "files": {
            "total": total_files,
            "this_week": files_this_week,
            "latest": (latest_upload.isoformat() + "Z") if latest_upload else None,
        },
        "online": {
            "now": sum(online_by_role.values()),
            "students": online_by_role.get("user", 0),
            "teachers": online_by_role.get("teacher", 0),
            "today": seen_today,
            "window_minutes": int(ONLINE_WINDOW.total_seconds() // 60),
        },
        "attention": {
            "approvals": pending_approvals,
            "deletions": pending_deletions,
            "oldest_approval_days": (date.today() - oldest_waiting).days if oldest_waiting else None,
        },
    }


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


def remove_material(db: Session, material: Material) -> str:
    """Delete everything behind one file: its record, the original on disk or Drive, and the AI's chunks from it.
    Returns the file's display name. Does not commit. A Drive failure raises 502 before anything else is touched,
    so the delete can simply be retried. Used by the school admin's Delete and when a teacher's request is approved."""
    from rag import delete_material_chunks
    if material.drive_file_id:
        try:
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
    return name


@router.delete("/files/{filename:path}")
def delete_school_file(filename: str, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """Delete one of this school's files: its record, the original on disk or Drive, and the AI's chunks from it."""
    material = db.query(Material).filter(Material.filename == filename, Material.school_id == user.school_id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="File not found")

    name = remove_material(db, material)
    db.add(AuditLog(actor=user.username, school_id=user.school_id, action="file.delete", target=name))
    db.commit()
    return {"message": f'Deleted "{name}".'}


@router.get("/audit-log")
def school_audit_log(limit: int = 200, section: Optional[str] = None, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """What happened in this school: sign-ups, approvals and rejections, certificate views, accounts created,
    files and subjects deleted, and who opened the lists of people's details (including teachers looking at student
    scores and their students). `section` narrows it to one part of the page (see audit.SECTIONS).
    The school comes from the signed-in account, so another school's events are unreachable."""
    query = db.query(AuditLog).filter(AuditLog.school_id == user.school_id)
    if section:
        if section not in SECTIONS:
            raise HTTPException(status_code=400, detail="Unknown section")
        query = query.filter(or_(*[AuditLog.action.startswith(prefix) for prefix in SECTIONS[section]]))
    rows = query.order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500))).all()
    return [{"at": r.created_at.isoformat() + "Z", "actor": r.actor, "action": r.action, "target": r.target, "detail": r.detail} for r in rows]
