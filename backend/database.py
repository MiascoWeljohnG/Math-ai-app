import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Get the Supabase URL from Render. If it doesn't exist (like on your local PC), use SQLite.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

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
