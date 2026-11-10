"""Sort the files already in Drive into one folder per school:

    <School name>/Modules/                    the course files
    <School name>/Certificate of Enrollment/  the students' certificate images

    python tools/organize_drive.py --dry-run    # only count what would move
    python tools/organize_drive.py              # do it

Only the database knows which school a file belongs to, so this reads it (DATABASE_URL in your .env). It must be the SAME
database the live app uses (your Supabase one): the script prints which database it is using, so check that first.
Files it can't match to a school are left exactly where they are and listed. Moving a file keeps its Drive id, so the app
keeps working and nothing in the database changes. Safe to run more than once. Needs the same four Drive settings as
check_drive.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import config  # noqa: E402  (also loads .env)
import drive_storage  # noqa: E402
from database import SessionLocal, engine  # noqa: E402
from models import Material, School, StudentCertificate, User  # noqa: E402


def build_placements(db) -> dict:
    """Drive file id -> (school name, kind), from the files and certificates the database knows about."""
    names = {school.id: school.name for school in db.query(School).all()}
    placements = {}
    for material in db.query(Material).filter(Material.drive_file_id.isnot(None)).all():
        placements[material.drive_file_id] = (names.get(material.school_id), drive_storage.MODULES)
    rows = db.query(StudentCertificate.storage_ref, User.school_id).join(User, User.id == StudentCertificate.user_id).all()
    for ref, school_id in rows:
        if ref.startswith("drive:"):
            placements[ref[len("drive:"):]] = (names.get(school_id), drive_storage.STUDENT_IMAGES)
    return placements


def main() -> int:
    dry = "--dry-run" in sys.argv
    missing = drive_storage._missing_settings()
    if missing:
        print("Missing settings:", ", ".join(missing))
        return 1
    print("Database:", engine.url.render_as_string(hide_password=True))
    if engine.dialect.name == "sqlite":
        print("WARNING: this is a local SQLite file, not your live database. It probably doesn't know your real files.")
    db = SessionLocal()
    try:
        placements = build_placements(db)
    finally:
        db.close()
    if not placements:
        print("The database lists no files stored in Drive, so there is nothing to sort. Is DATABASE_URL the live one?")
        return 1
    try:
        print("Folder:", repr(drive_storage.check()))
        result = drive_storage.organize_existing(placements, dry_run=dry)
    except drive_storage.DriveStorageError as exc:
        print("FAILED:", exc)
        return 1
    verb = "Would move" if dry else "Moved"
    for (school, kind), count in sorted(result["moved"].items()):
        print(f"{verb} {count} file(s) to {school}/{drive_storage._FOLDER_NAMES[kind]}")
    if not result["moved"]:
        print("Nothing to move.")
    if result["unknown"]:
        shown = ", ".join(result["unknown"][:10]) + (" ..." if len(result["unknown"]) > 10 else "")
        print(f"Left alone ({len(result['unknown'])}, not found in the database): {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
