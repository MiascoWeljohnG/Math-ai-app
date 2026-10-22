"""Check the Drive settings before you deploy: opens the folder, uploads a small test file, reads it back,
then moves it to the trash. Run from the backend folder with the four values in .env (or exported):

    python tools/check_drive.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import config  # noqa: E402  (also loads .env)
import drive_storage  # noqa: E402


def main() -> int:
    missing = drive_storage._missing_settings()
    if missing:
        print("Missing settings:", ", ".join(missing))
        return 1
    try:
        print("Folder:", repr(drive_storage.check()))
        payload = b"drive check - safe to delete"
        file_id = drive_storage.upload_bytes("drive-check.txt", payload)
        print("Uploaded test file:", file_id)
        assert drive_storage.download_bytes(file_id) == payload, "downloaded bytes differ from what was uploaded"
        print("Read it back: OK")
        drive_storage.delete_file(file_id)
        print("Moved it to the trash: OK\n\nGoogle Drive storage works.")
        return 0
    except drive_storage.DriveStorageError as exc:
        print("FAILED:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
