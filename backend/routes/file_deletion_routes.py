"""Deleting an uploaded file. A teacher can only ASK to delete a file they uploaded; the admin of their school decides.
Approving deletes the file for good (its record, the original, and what the AI learned from it); rejecting keeps it.
Everything is limited to the requester's own school, and each request and decision goes into the audit log."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_school_admin, require_teacher
from database import get_db
from models import AuditLog, FileDeletionRequest, Material, User
from notifications import notify_admins
from routes.school_admin_routes import remove_material

router = APIRouter(prefix="/file-deletions", tags=["file-deletions"])

REJECTION_SHOWN_FOR = timedelta(days=14)   # how long a teacher keeps seeing "the admin declined" under the file


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() + "Z" if moment else None


class FileDeletionBody(BaseModel):
    filename: str
    reason: Optional[str] = Field(default=None, max_length=300)


@router.post("")
def request_file_deletion(req: FileDeletionBody, user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    # A teacher can only ask about their own uploads. Anything else looks like it does not exist.
    material = db.query(Material).filter(
        Material.filename == req.filename,
        Material.uploaded_by == user.username,
        Material.school_id == user.school_id,
    ).first()
    if material is None:
        raise HTTPException(status_code=404, detail="File not found")
    if db.query(FileDeletionRequest).filter(FileDeletionRequest.filename == material.filename, FileDeletionRequest.status == "pending").first():
        raise HTTPException(status_code=409, detail="A deletion request for this file is already waiting for the school admin")

    reason = (req.reason or "").strip() or None
    db.add(FileDeletionRequest(
        filename=material.filename, display_name=material.display_name,
        requested_by=user.username, school_id=user.school_id, reason=reason,
    ))
    db.add(AuditLog(actor=user.username, school_id=user.school_id, action="file.delete.request", target=material.display_name, detail=reason))
    notify_admins(db, "file_deletion_request", "File deletion requested",
                  f'@{user.username} asked to delete "{material.display_name}".', school_id=user.school_id)
    db.commit()
    return {"status": "pending", "message": f'Request sent. "{material.display_name}" will be deleted once your school admin approves.'}


@router.get("/mine")
def my_requests(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """What happened to this teacher's requests: the ones still waiting, and recently declined ones, so the
    Uploaded Files table can say so under the file."""
    since = datetime.utcnow() - REJECTION_SHOWN_FOR
    rows = db.query(FileDeletionRequest).filter(FileDeletionRequest.requested_by == user.username).order_by(FileDeletionRequest.id.asc()).all()
    latest = {}
    for row in rows:   # the newest request per file wins (a file can be asked about again after a decline)
        latest[row.filename] = row
    return [
        {"filename": name, "status": row.status}
        for name, row in latest.items()
        if row.status == "pending" or (row.status == "rejected" and row.resolved_at and row.resolved_at >= since)
    ]


@router.get("")
def list_requests(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """The requests waiting for this school admin's answer, oldest first."""
    rows = (
        db.query(FileDeletionRequest)
        .filter(FileDeletionRequest.status == "pending", FileDeletionRequest.school_id == user.school_id)
        .order_by(FileDeletionRequest.created_at.asc(), FileDeletionRequest.id.asc())
        .all()
    )
    names = {u.username: u.person_name for u in db.query(User).filter(User.school_id == user.school_id)}
    result, changed = [], False
    for row in rows:
        material = db.query(Material).filter(Material.filename == row.filename, Material.school_id == user.school_id).first()
        if material is None:   # the file is already gone (the admin deleted it directly): nothing left to decide
            row.status, row.resolved_at, changed = "approved", datetime.utcnow(), True
            continue
        result.append({
            "id": row.id,
            "filename": row.filename,
            "display_name": material.display_name,
            "branch": material.branch,
            "requested_by": row.requested_by,
            "requested_by_name": names.get(row.requested_by, ""),
            "reason": row.reason,
            "created_at": _iso(row.created_at),
        })
    if changed:
        db.commit()
    return result


class Decision(BaseModel):
    approve: bool


@router.post("/{request_id}/decision")
def decide(request_id: int, req: Decision, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    request = db.query(FileDeletionRequest).filter(FileDeletionRequest.id == request_id, FileDeletionRequest.school_id == user.school_id).first()
    if request is None:   # another school's request looks like it does not exist
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"This request was already {request.status}")

    name = request.display_name
    if req.approve:
        material = db.query(Material).filter(Material.filename == request.filename, Material.school_id == user.school_id).first()
        if material is not None:
            name = remove_material(db, material)   # a Drive failure raises here and leaves the request pending
        message = f'Approved. "{name}" was deleted.'
    else:
        message = f'Rejected. "{name}" stays.'
    request.status = "approved" if req.approve else "rejected"
    request.resolved_at, request.decided_by = datetime.utcnow(), user.username
    db.add(AuditLog(actor=user.username, school_id=user.school_id, action="file.delete.approve" if req.approve else "file.delete.reject", target=name))
    db.commit()
    return {"status": request.status, "message": message}
