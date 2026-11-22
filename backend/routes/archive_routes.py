"""The school admin's Archive and File deletion pages. Everything a teacher deleted (files, lessons, subjects) waits in the archive
for 30 days; the admin can see it there, and once the 30 days have passed the admin deletes it for good. Always limited to the admin's
own school (it comes from the signed-in account, never from the request)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import archive
from auth import require_school_admin
from database import get_db
from models import ArchivedItem, User
from notifications import notify_admins

router = APIRouter(prefix="/archive", tags=["archive"])


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() + "Z" if moment else None


def _mine(db: Session, user: User):
    return db.query(ArchivedItem).filter(ArchivedItem.school_id == user.school_id)


@router.get("")
def list_archive(kind: Optional[str] = None, due: Optional[bool] = None, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """This school's archived items, newest first. `kind` = file | lesson | subject; `due=true` = only the ones whose 30 days
    have passed (the File deletion page), `due=false` = only the ones still inside the 30 days."""
    if kind is not None and kind not in archive.KINDS:
        raise HTTPException(status_code=400, detail="Unknown kind")
    query = _mine(db, user)
    if kind:
        query = query.filter(ArchivedItem.kind == kind)
    names = {u.username: u.person_name for u in db.query(User).filter(User.school_id == user.school_id)}
    now = datetime.utcnow()
    result = []
    for item in query.order_by(ArchivedItem.archived_at.desc(), ArchivedItem.id.desc()).all():
        is_due = archive.is_due(item, now)
        if due is not None and is_due != due:
            continue
        result.append({
            "id": item.id, "kind": item.kind, "title": item.title, "context": item.context, "reason": item.reason,
            "archived_by": item.archived_by, "archived_by_name": names.get(item.archived_by, ""),
            "archived_at": _iso(item.archived_at), "expires_at": _iso(archive.expires_at(item)),
            "days_left": archive.days_left(item, now), "due": is_due,
        })
    return result


@router.post("/purge-due")
def purge_all_due(user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """Delete permanently every item of this school whose 30 days have passed. One failing item (e.g. Drive is down) does not
    stop the rest; it stays in the archive and is named in `failed`."""
    now = datetime.utcnow()
    deleted, failed = 0, []
    for item in _mine(db, user).order_by(ArchivedItem.archived_at.asc()).all():
        if not archive.is_due(item, now):
            continue
        title = item.title
        try:
            archive.purge_item(db, item, user.username)
            db.commit()
            deleted += 1
        except HTTPException:
            db.rollback()
            failed.append(title)
    message = f"Permanently deleted {deleted} item{'' if deleted == 1 else 's'}."
    if failed:
        message += f" Couldn't delete: {', '.join(failed)}. Try again later."
    return {"deleted": deleted, "failed": failed, "message": message}


@router.post("/{item_id}/purge")
def purge_one(item_id: int, user: User = Depends(require_school_admin), db: Session = Depends(get_db)):
    """Delete one archived item permanently. Only allowed once its 30 days have passed."""
    item = _mine(db, user).filter(ArchivedItem.id == item_id).first()
    if item is None:   # another school's item looks like it does not exist
        raise HTTPException(status_code=404, detail="Item not found")
    if not archive.is_due(item):
        raise HTTPException(status_code=409, detail=f"This item can be deleted permanently in {archive.days_left(item)} day(s).")
    title = archive.purge_item(db, item, user.username)
    db.commit()
    return {"message": f'"{title}" was permanently deleted.'}
