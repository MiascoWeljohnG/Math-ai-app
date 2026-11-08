"""Student approval queue.

Only school admins review, and only the students of their own school. The school comes from the signed-in
account (never from the request). A student of another school is answered with 404, not 403, so usernames of
the other school cannot be probed.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import certificates
from auth import require_school_admin
from database import get_db
from models import ACTIVE, PENDING, REJECTED, AuditLog, School, StudentCertificate, User

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _in_scope(query, reviewer: User):
    return query.filter(User.role == "user", User.school_id == reviewer.school_id)


def _student_or_404(db: Session, reviewer: User, username: str) -> User:
    student = _in_scope(db.query(User), reviewer).filter(User.username == username).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


def _latest_certificate(db: Session, student: User) -> StudentCertificate | None:
    return db.query(StudentCertificate).filter(StudentCertificate.user_id == student.id).order_by(StudentCertificate.id.desc()).first()


@router.get("/pending")
def list_pending(reviewer: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """The students waiting for a decision, oldest first, with the hints a reviewer needs."""
    students = _in_scope(db.query(User), reviewer).filter(User.status == PENDING).order_by(User.id.asc()).all()
    schools = {s.id: s.name for s in db.query(School)}
    items = []
    for s in students:
        cert = _latest_certificate(db, s)
        reused = bool(cert) and db.query(StudentCertificate).filter(StudentCertificate.sha256 == cert.sha256, StudentCertificate.user_id != s.id).count() > 0
        items.append({
            "username": s.username, "last_name": s.last_name, "first_name": s.first_name, "middle_name": s.middle_name,
            "email": s.email, "birthday": s.birthday, "school_id": s.school_id, "school": schools.get(s.school_id),
            "submitted": (cert.uploaded_at.isoformat() + "Z") if cert and cert.uploaded_at else None,
            "attempt": s.submissions or 1,
            "certificate": {"type": cert.content_type, "size": cert.size_bytes} if cert else None,
            "certificate_reused": reused,     # the same file was uploaded by another account
        })
    return items


@router.get("/{username}/certificate")
def view_certificate(username: str, reviewer: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    student = _student_or_404(db, reviewer, username)
    cert = _latest_certificate(db, student)
    if cert is None:
        raise HTTPException(status_code=404, detail="No certificate on file")
    db.add(AuditLog(actor=reviewer.username, school_id=student.school_id, action="certificate.view", target=student.username))
    db.commit()
    ext = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}[cert.content_type]
    return Response(
        content=certificates.load(cert.storage_ref),
        media_type=cert.content_type,   # decided from the file's bytes when it was uploaded
        headers={
            "Content-Disposition": f'inline; filename="certificate.{ext}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "no-store",
        },
    )


def _decide(db: Session, reviewer: User, student: User, new_status: str, reason: str | None) -> None:
    # One conditional UPDATE: if two reviewers act at once, exactly one wins and the other gets a 409.
    changed = db.query(User).filter(User.id == student.id, User.status == PENDING).update(
        {"status": new_status, "reviewed_by": reviewer.username, "reviewed_at": datetime.utcnow(), "rejection_reason": reason},
        synchronize_session=False,
    )
    if not changed:
        db.rollback()
        raise HTTPException(status_code=409, detail="This registration was already decided.")
    action = "student.approve" if new_status == ACTIVE else "student.reject"
    db.add(AuditLog(actor=reviewer.username, school_id=student.school_id, action=action, target=student.username, detail=reason))
    db.commit()


@router.post("/{username}/approve")
def approve(username: str, reviewer: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    student = _student_or_404(db, reviewer, username)
    _decide(db, reviewer, student, ACTIVE, None)
    return {"message": f"{username} approved. They can log in now."}


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=200)   # shown to the student, so it is required


@router.post("/{username}/reject")
def reject(username: str, req: RejectRequest, reviewer: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    student = _student_or_404(db, reviewer, username)
    _decide(db, reviewer, student, REJECTED, " ".join(req.reason.split()))
    return {"message": f"{username} rejected."}
