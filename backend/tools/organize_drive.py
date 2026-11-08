"""Tidy the Drive storage folder: move the files that were uploaded before the sub-folders existed into
Modules/ (course files) and Certificate of Enrollment/ (certificate images, names starting with cert_).

    python tools/organize_drive.py --dry-run    # only count what would move
    python tools/organize_drive.py              # do it

Safe to run more than once: files already inside a sub-folder are left alone. Moving a file keeps its Drive id,
so the app keeps working and nothing in the database changes. Needs the same four Drive settings as check_drive.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import config  # noqa: E402  (also loads .env)
import drive_storage  # noqa: E402


def main() -> int:
    dry = "--dry-run" in sys.argv
    missing = drive_storage._missing_settings()
    if missing:
        print("Missing settings:", ", ".join(missing))
        return 1
    try:
        print("Folder:", repr(drive_storage.check()))
        moved = drive_storage.organize_existing(dry_run=dry)
    except drive_storage.DriveStorageError as exc:
        print("FAILED:", exc)
        return 1
    verb = "Would move" if dry else "Moved"
    print(f"{verb} {moved[drive_storage.MODULES]} file(s) to Modules and {moved[drive_storage.STUDENT_IMAGES]} to Certificate of Enrollment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
