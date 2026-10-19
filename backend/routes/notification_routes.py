"""The admin bell: what the AI wasn't sure about, uploads by teachers, deleted files, deletion requests."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])
KEEP_LATEST = 50   # the bell shows the newest 50; older ones are trimmed when the list is read


def _mine(db: Session, user: User):
    return db.query(Notification).filter(Notification.admin_username == user.username)


@router.get("")
def list_notifications(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = _mine(db, user).order_by(Notification.created_at.desc(), Notification.id.desc()).all()
    for old in rows[KEEP_LATEST:]:
        db.delete(old)
    if len(rows) > KEEP_LATEST:
        db.commit()
    return {
        "unread": sum(1 for n in rows[:KEEP_LATEST] if not n.read),
        "items": [
            {
                "id": n.id, "kind": n.kind, "title": n.title, "message": n.message, "read": n.read,
                "created_at": n.created_at.isoformat() + "Z" if n.created_at else None,   # UTC; Z lets the browser localise it
            }
            for n in rows[:KEEP_LATEST]
        ],
    }


@router.post("/read-all")
def mark_all_read(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _mine(db, user).filter(Notification.read.is_(False)).update({"read": True})
    db.commit()
    return {"message": "All notifications marked as read."}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = _mine(db, user).filter(Notification.id == notification_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.read = True
    db.commit()
    return {"message": "ok"}


@router.delete("")
def clear_notifications(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _mine(db, user).delete()
    db.commit()
    return {"message": "Notifications cleared."}
