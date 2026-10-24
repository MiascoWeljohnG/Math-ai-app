"""Startup guarantees for the account system. Each function is idempotent (safe on every start)."""
import logging

from sqlalchemy.orm import Session

import config
from auth import hash_password, verify_password
from models import ACTIVE, DISABLED, School, Subject, User
from progress import BRANCHES

log = logging.getLogger(__name__)
LEGACY_DEFAULT_PASSWORD = "admin123"   # what older versions of this app created the admin with


def ensure_schools(db: Session) -> None:
    """Create the two fixed schools (with the usual starting subjects) if missing."""
    existing = {s.name for s in db.query(School)}
    for name in config.SCHOOL_NAMES:
        if name in existing:
            continue
        school = School(name=name)
        db.add(school)
        db.flush()
        db.add_all(Subject(name=branch, school_id=school.id) for branch in BRANCHES)
    db.commit()
    extras = existing - set(config.SCHOOL_NAMES)
    if extras:   # left over from before the two-school rule; never deleted automatically (it would orphan data)
        log.warning("Schools outside the fixed set exist in the database: %s. Move their users, then remove them.", sorted(extras))


def ensure_school_admins(db: Session) -> None:
    """Each of the two schools has one default admin. If a school already has an active admin nothing happens;
    otherwise one is created from SCHOOLn_ADMIN_USERNAME / SCHOOLn_ADMIN_PASSWORD. There is no built-in
    password: with none configured the server says so and creates nothing."""
    for school_name, (username, password) in zip(config.SCHOOL_NAMES, config.SCHOOL_ADMIN_DEFAULTS):
        school = db.query(School).filter(School.name == school_name).first()
        if school is None:
            continue
        if db.query(User).filter(User.role == "school_admin", User.school_id == school.id, User.status == ACTIVE).first():
            continue
        if not password:
            log.error("%s has no admin. Set SCHOOL%d_ADMIN_PASSWORD (and optionally SCHOOL%d_ADMIN_USERNAME) and restart, "
                      "or run `python create_admin.py`.", school_name, config.SCHOOL_NAMES.index(school_name) + 1, config.SCHOOL_NAMES.index(school_name) + 1)
            continue
        if len(password) < config.ADMIN_MIN_PASSWORD_LENGTH:
            raise RuntimeError(f"The admin password for {school_name} must be at least {config.ADMIN_MIN_PASSWORD_LENGTH} characters.")
        if db.query(User).filter(User.username == username).first():
            raise RuntimeError(f"Cannot create the {school_name} admin: the username {username!r} is already taken.")
        db.add(User(
            username=username, first_name=school_name, last_name="Admin", middle_name="", birthday="2000-01-01",
            password_hash=hash_password(password), role="school_admin", school_id=school.id, status=ACTIVE,
        ))
        db.commit()
        log.info("Created the default admin %r for %s.", username, school_name)


def retire_main_admins(db: Session) -> None:
    """The old all-schools admin role no longer exists. Any account still holding it is disabled (kept in the
    database, so nothing it created is orphaned, but it can no longer sign in)."""
    for old in db.query(User).filter(User.role == "admin", User.status != DISABLED):
        old.status = DISABLED
        log.warning("Disabled the old main admin account %r (that role was removed).", old.username)
    db.commit()


def warn_if_default_password(db: Session) -> None:
    for admin in db.query(User).filter(User.role == "school_admin", User.status == ACTIVE):
        try:
            weak = verify_password(LEGACY_DEFAULT_PASSWORD, admin.password_hash)
        except Exception:
            weak = False
        if weak:
            log.critical("Admin %r still uses the old default password. Change it now.", admin.username)
