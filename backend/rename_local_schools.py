import datetime
import shutil
import sqlite3
from pathlib import Path

DB = Path(__file__).with_name("app.db")
EXPECTED = [
    (1, "School A"),
    (2, "School B"),
    (3, "Saint Mark's Institute"),
    (4, "Cavite State University Bacoor Campus"),
]

conn = sqlite3.connect(DB)
try:
    conn.execute("PRAGMA foreign_keys=ON")
    actual = conn.execute("SELECT id, name FROM schools ORDER BY id").fetchall()
    if actual != EXPECTED:
        raise SystemExit(f"Database school rows differ from expected; no changes made: {actual!r}")

    # The duplicate schools have generated subjects, but no lessons or school-scoped
    # materials/audit rows. Preserve users/subjects by moving them to canonical IDs.
    checks = [
        ("duplicate-school lessons", "SELECT 1 FROM subjects s JOIN lessons l ON l.subject_id=s.id WHERE s.school_id IN (3,4) LIMIT 1"),
        ("duplicate-school materials", "SELECT 1 FROM materials WHERE school_id IN (3,4) LIMIT 1"),
        ("duplicate-school audit rows", "SELECT 1 FROM audit_log WHERE school_id IN (3,4) LIMIT 1"),
    ]
    for label, sql in checks:
        if conn.execute(sql).fetchone():
            raise SystemExit(f"Found {label}; no changes made. Requires a more detailed merge.")

    backup = DB.with_name(
        "app.db.before_school_cleanup_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".bak"
    )
    shutil.copy2(DB, backup)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE schools SET name=? WHERE id=3", ("__merge_school_3__",))
        conn.execute("UPDATE users SET school_id=1 WHERE school_id=3")
        conn.execute("UPDATE subjects SET school_id=1 WHERE school_id=3")
        conn.execute("UPDATE schools SET name=? WHERE id=1", ("Saint Mark's Institute",))

        conn.execute("UPDATE schools SET name=? WHERE id=4", ("__merge_school_4__",))
        conn.execute("UPDATE users SET school_id=2 WHERE school_id=4")
        conn.execute("UPDATE subjects SET school_id=2 WHERE school_id=4")
        conn.execute("UPDATE schools SET name=? WHERE id=2", ("Cavite State University Bacoor Campus",))
        conn.execute("DELETE FROM schools WHERE id IN (3,4)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    print(f"Backup created: {backup}")
    print("Schools:", conn.execute("SELECT id, name FROM schools ORDER BY id").fetchall())
    print("School-linked users:", conn.execute("SELECT username, role, school_id FROM users WHERE school_id IS NOT NULL ORDER BY id").fetchall())
    print("Subject totals:", conn.execute("SELECT school_id, COUNT(*) FROM subjects GROUP BY school_id ORDER BY school_id").fetchall())
    print("Foreign key check:", conn.execute("PRAGMA foreign_key_check").fetchall())
finally:
    conn.close()
