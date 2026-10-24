"""Recovery tool: create the admin of a school that has none (for example if the SCHOOLn_ADMIN_PASSWORD variables
were missing on the first start).

    python create_admin.py

A school only ever has its one default admin, so this refuses to run for a school that already has one. It asks
for the password (never a command-line argument, so it stays out of shell history) and works against whichever
database DATABASE_URL points to (SQLite or Supabase).
"""
import getpass
import sys

import config
from auth import check_password_strength, hash_password
from bootstrap import ensure_schools
from database import Base, SessionLocal, engine, migrate_add_missing_columns, backfill_user_status
from models import ACTIVE, School, User

Base.metadata.create_all(bind=engine)
migrate_add_missing_columns()
backfill_user_status()
db = SessionLocal()
ensure_schools(db)

missing = [s for s in db.query(School).order_by(School.id)
           if not db.query(User).filter(User.role == "school_admin", User.school_id == s.id, User.status == ACTIVE).first()]
if not missing:
    sys.exit("Both schools already have an admin. Nothing to do.")

print("Schools without an admin:")
for i, school in enumerate(missing, 1):
    print(f"  {i}. {school.name}")
school = missing[int(input("Choose a number: ")) - 1]
default_name = config.SCHOOL_ADMIN_DEFAULTS[config.SCHOOL_NAMES.index(school.name)][0]
username = input(f"Username [{default_name}]: ").strip() or default_name
if db.query(User).filter(User.username == username).first():
    sys.exit(f"The username {username!r} is already taken.")
password = getpass.getpass(f"Password (at least {config.ADMIN_MIN_PASSWORD_LENGTH} characters): ")
check_password_strength(password, config.ADMIN_MIN_PASSWORD_LENGTH)
if password != getpass.getpass("Repeat the password: "):
    sys.exit("The passwords do not match.")

db.add(User(
    username=username, first_name=school.name, last_name="Admin", middle_name="", birthday="2000-01-01",
    password_hash=hash_password(password), role="school_admin", school_id=school.id, status=ACTIVE,
))
db.commit()
print(f"Admin {username!r} created for {school.name}.")
