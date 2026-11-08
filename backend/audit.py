"""Audit trail helpers.

Changes (approve, reject, delete, create...) are written to the log right where they happen. This module covers the
other half: a row saying WHO OPENED a list of people's details, and WHEN, plus the grouping the school admin's log
filter uses to show one section at a time."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from models import AuditLog, User

logger = logging.getLogger(__name__)

# Opening the same list again inside this window (auto-refresh, switching tabs, changing a filter) is one log entry,
# so the log stays readable and a page left open does not fill it. It is decided here on the server, never by the browser.
VIEW_WINDOW = timedelta(minutes=30)

# Which actions belong to which section of the school admin's page. A section is a list of action prefixes.
SECTIONS = {
    "people": ("teacher.create", "school_admin.create", "users."),            # teachers and students list
    "approvals": ("student.", "certificate.", "approvals."),                  # pending approvals
    "subject_deletions": ("subject.delete",),                                 # subject deletion requests
    "file_deletions": ("file.delete",),                                       # file deletion requests
    "scores_roster": ("scores.", "roster."),                                  # teacher side: Student Scores, Your Students
}


def log_view(db: Session, user: User, action: str, target: Optional[str] = None, detail: Optional[str] = None) -> None:
    """Record that `user` opened a list of people's details. Once per (person, list, target) per VIEW_WINDOW.

    Call it AFTER the response data is built: it commits, which expires loaded ORM objects. A failure to write the
    row is logged and swallowed so a log problem never takes the page down."""
    try:
        same_target = AuditLog.target.is_(None) if target is None else AuditLog.target == target
        recent = db.query(AuditLog.id).filter(
            AuditLog.actor == user.username,
            AuditLog.action == action,
            same_target,
            AuditLog.created_at >= datetime.utcnow() - VIEW_WINDOW,
        ).first()
        if recent is not None:
            return
        db.add(AuditLog(actor=user.username, school_id=user.school_id, action=action, target=target, detail=detail))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not write the audit entry %s for %s", action, getattr(user, "username", "?"))
