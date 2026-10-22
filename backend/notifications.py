"""The admin bell. notify_admins() writes one Notification row per admin; routes/notification_routes.py reads them."""
from sqlalchemy.orm import Session

from models import Notification, User


def notify_admins(db: Session, kind: str, title: str, message: str = "", exclude: str | None = None) -> None:
    """Add a bell entry for every admin (except `exclude`, usually the person who did the action).
    Only adds to the session; the caller commits together with its own change."""
    for (username,) in db.query(User.username).filter(User.role == "admin"):
        if username != exclude:
            db.add(Notification(admin_username=username, kind=kind, title=title, message=message))
