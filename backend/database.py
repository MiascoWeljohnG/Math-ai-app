import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Get the Supabase URL from Render. If it doesn't exist (like on your local PC), use SQLite.
# Anchor the default SQLite database path to the backend directory so it resolves
# consistently regardless of the working directory the server was launched from.
_DEFAULT_DB = f"sqlite:///{(Path(__file__).resolve().parent / 'app.db').as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_DB)

# PostgreSQL (Supabase) and SQLite require different connection setups
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def migrate_add_missing_columns():
    """Add model columns missing from an existing database after create_all()."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    col_type = col.type.compile(engine.dialect)
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}"))


def backfill_user_status():
    """Accounts that existed before the approval workflow have no status. They were already trusted, so they
    become 'active'. Safe to run on every start: new rows always carry an explicit status."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if not inspector.has_table("users") or "status" not in {c["name"] for c in inspector.get_columns("users")}:
        return
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET status = 'active' WHERE status IS NULL"))


def drop_legacy_full_name():
    """The users table no longer has a full_name column (last / first / middle name are separate).
    Copy any name that only lived in full_name into first_name, then drop the column.
    Safe to run on every start: it does nothing once the column is gone."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return
    if "full_name" not in {c["name"] for c in inspector.get_columns("users")}:
        return
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE users SET first_name = full_name "
            "WHERE (first_name IS NULL OR first_name = '') AND full_name IS NOT NULL AND full_name <> ''"
        ))
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users DROP COLUMN full_name"))
    except Exception as exc:   # very old SQLite (< 3.35) cannot drop columns; the nullable column is harmless
        print(f"[migrate] could not drop users.full_name: {exc}")


def backfill_subject_managers():
    """Shared subjects made before subjects had a managing teacher: credit the teacher of the same school who wrote the subject's
    first lesson. A subject with no lessons stays unclaimed (the first teacher to edit it claims it). Safe to run on every start:
    it only fills subjects that have no manager yet."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if not inspector.has_table("subjects") or "manager_id" not in {c["name"] for c in inspector.get_columns("subjects")}:
        return
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE subjects SET manager_id = ("
            " SELECT u.id FROM lessons l JOIN users u ON u.username = l.created_by"
            " WHERE l.subject_id = subjects.id AND u.role = 'teacher'"
            " AND (u.school_id = subjects.school_id OR (u.school_id IS NULL AND subjects.school_id IS NULL))"
            " ORDER BY l.id ASC LIMIT 1) "
            "WHERE manager_id IS NULL AND owner_user_id IS NULL"))


def sync_id_sequences():
    """PostgreSQL only. Rows copied in with their own ids (a move from SQLite, or typed into the Supabase table editor) can leave a
    table's id counter at or behind its highest id, so the next INSERT fails with "duplicate key value violates unique constraint
    ..._pkey". Move any such counter up to the highest id. Safe to run on every start: it never moves a counter backwards."""
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if "id" not in table.columns or not table.columns["id"].primary_key or not inspector.has_table(table.name):
            continue
        quoted = '"' + table.name.replace('"', '""') + '"'
        try:
            with engine.begin() as conn:
                sequence = conn.execute(text("SELECT pg_get_serial_sequence(:table, 'id')"), {"table": quoted}).scalar()
                if not sequence:
                    continue
                top = conn.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {quoted}")).scalar() or 0
                counter = conn.execute(text(f"SELECT last_value FROM {sequence}")).scalar() or 0
                if top > 0 and top >= counter:
                    conn.execute(text("SELECT setval(CAST(:sequence AS regclass), :top)"), {"sequence": sequence, "top": top})
        except Exception as exc:   # an odd permission or a table without a serial id: leave it alone
            print(f"[migrate] could not sync the id counter of {table.name}: {exc}")
