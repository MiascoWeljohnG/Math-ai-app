import getpass
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from auth import hash_password

DB = Path(__file__).with_name("app.db")
conn = sqlite3.connect(DB)
try:
    rows = conn.execute("SELECT id, username, school_id, role FROM users WHERE username IN (?, ?) ORDER BY username", ("school1_admin", "school2_admin")).fetchall()
    if len(rows) != 2 or any(row[3] != "school_admin" for row in rows):
        raise SystemExit(f"Expected both school admin accounts; found {[(r[1], r[2], r[3]) for r in rows]}")
    print("Accounts to update:")
    for row in rows:
        print(f"  {row[1]} (school_id={row[2]}, role={row[3]})")
    first = getpass.getpass("New password for school1_admin (min 12 characters): ")
    second = getpass.getpass("New password for school2_admin (min 12 characters): ")
    if len(first) < 12 or len(second) < 12:
        raise SystemExit("Both passwords must be at least 12 characters. No database changes made.")
    if first == second:
        print("Note: both accounts will use the same password.")
    backup = DB.with_name(DB.name + ".before_admin_password_reset_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".bak")
    shutil.copy2(DB, backup)
    hashes = {"school1_admin": hash_password(first), "school2_admin": hash_password(second)}
    conn.execute("BEGIN IMMEDIATE")
    for username, password_hash in hashes.items():
        conn.execute("UPDATE users SET password_hash=? WHERE username=? AND role='school_admin'", (password_hash, username))
    conn.commit()
    print(f"Passwords updated. Backup: {backup.name}")
finally:
    conn.close()
