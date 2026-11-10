"""What "same school" means, in one place. school_id None is the main pool (everything made before
schools existed, plus the main admin), and it only matches itself, so old data keeps working."""
from sqlalchemy import and_, or_

from models import Subject, User


def in_school(column, school_id):
    """SQL filter: rows of one school. NULL needs IS NULL, `== None` would be wrong in SQL."""
    return column.is_(None) if school_id is None else column == school_id


def shared_subjects(user: User):
    """SQL filter: the shared (teacher-made) subjects of the user's own school."""
    return and_(Subject.owner_user_id.is_(None), in_school(Subject.school_id, user.school_id))


def visible_subjects(user: User):
    """SQL filter: those, plus the user's personal subjects."""
    return or_(shared_subjects(user), Subject.owner_user_id == user.id)


def school_name(db, school_id):
    """The name of a school (used for its Drive folder), or None for the main pool and for an unknown id."""
    if school_id is None:
        return None
    from models import School
    row = db.query(School.name).filter(School.id == school_id).first()
    return row[0] if row else None
