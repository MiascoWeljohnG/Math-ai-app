"""The admin bell. notify_admins() writes one Notification row per admin of a school; routes/notification_routes.py
reads them. Each school's admin only ever hears about their own school."""
from sqlalchemy.orm import Session

from models import Notification, User


def notify_admins(db: Session, kind: str, title: str, message: str = "", exclude: str | None = None,
                  school_id: int | None = None, about: str | None = None) -> None:
    """Add a bell entry for the school's admin(s), except `exclude` (usually the person who did the action).
    The school is `school_id`, or the school of the account named in `about` (e.g. the uploader). With neither,
    nobody is notified. Only adds to the session; the caller commits together with its own change."""
    if school_id is None and about:
        school_id = db.query(User.school_id).filter(User.username == about).scalar()
    if school_id is None:
        return
    for (username,) in db.query(User.username).filter(User.role == "school_admin", User.school_id == school_id):
        if username != exclude:
            db.add(Notification(admin_username=username, kind=kind, title=title, message=message))
