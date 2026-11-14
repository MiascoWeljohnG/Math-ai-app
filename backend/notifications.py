"""The bells. notify_admins() writes one Notification row per admin of a school; notify_teacher(s)() write the
teacher's (upload and lesson results, quiz violations); routes/notification_routes.py reads them. A school's staff only
ever hear about their own school."""
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


def notify_user(db: Session, username: str, kind: str, title: str, message: str = "") -> None:
    """Add a bell entry for one account. Only adds to the session; the caller commits."""
    db.add(Notification(admin_username=username, kind=kind, title=title, message=message))


def notify_teacher(db: Session, username: str, kind: str, title: str, message: str = "") -> None:
    """Bell entry for `username`, only if that account is a teacher. Lets code shared with students and admins
    (an upload, a lesson written by the AI) report back to a teacher without changing what anyone else sees."""
    if db.query(User.id).filter(User.username == username, User.role == "teacher").first() is not None:
        notify_user(db, username, kind, title, message)


def notify_teachers(db: Session, school_id: int | None, kind: str, title: str, message: str = "") -> None:
    """Bell entry for every active teacher of a school (school_id None = the main pool)."""
    from models import ACTIVE
    from school import in_school
    for (username,) in db.query(User.username).filter(User.role == "teacher", User.status == ACTIVE, in_school(User.school_id, school_id)):
        notify_user(db, username, kind, title, message)
