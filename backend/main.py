import logging
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, SessionLocal, migrate_add_missing_columns, drop_legacy_full_name, backfill_user_status
from models import User, Subject
from bootstrap import ensure_schools, ensure_school_admins, retire_main_admins, warn_if_default_password
from routes import approval_routes, auth_routes, user_routes, teacher_routes, materials_routes, profile_routes, subjects_routes, subject_deletion_routes, notification_routes, learning_routes, schools_routes, school_admin_routes, practice_routes
import config

Base.metadata.create_all(bind=engine)
migrate_add_missing_columns()
drop_legacy_full_name()
backfill_user_status()   # accounts from before the approval workflow stay usable

db = SessionLocal()
ensure_schools(db)        # exactly the two configured schools
ensure_school_admins(db)  # one default admin per school; no built-in password: see bootstrap.py
retire_main_admins(db)    # the all-schools admin role no longer exists
warn_if_default_password(db)
# Seed the four default branches only on a brand-new database. Seeding "any that is missing" on every
# start would bring back a subject the admins just approved deleting.
if not db.query(Subject).filter(Subject.owner_user_id.is_(None)).first():
    for subject_name in ("Algebra", "Geometry", "Statistics", "Calculus"):
        db.add(Subject(name=subject_name))
db.commit()
db.close()

from rag import ingest_uploads, chroma_client
from models import Material
import drive_storage
import threading

log = logging.getLogger(__name__)


def _sync_drive_index_at_startup():
    """Rebuild the AI's search index from the files in Google Drive. Render wipes its disk (and with it the
    index) on every restart, so this is what brings the knowledge base back. It runs in the background so the
    server starts answering right away; until it finishes, material questions may find nothing."""
    from rag import sync_drive_index
    session = SessionLocal()
    try:
        folder = drive_storage.check()
        rows = session.query(Material).filter(Material.drive_file_id.isnot(None)).all()
        files = [(m.filename, m.branch or "General", m.drive_file_id) for m in rows]
        log.info("Drive storage OK (folder %r). Indexing %d file(s)...", folder, len(files))
        result = sync_drive_index(files)
        log.info("Drive index ready: %s", result)
    except Exception:
        log.exception("Couldn't sync the Drive files into the search index")
    finally:
        session.close()


# Index the uploaded files (the knowledge base). If anything here fails the app must still start,
# otherwise every request fails and the browser just says "Failed to fetch".
if drive_storage.enabled():
    threading.Thread(target=_sync_drive_index_at_startup, name="drive-index-sync", daemon=True).start()
else:
    if os.getenv("RENDER"):
        log.warning("Uploads are stored on Render's local disk and will be LOST on every redeploy/restart. "
                    "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN and DRIVE_FOLDER_ID to use Google Drive.")
    try:
        ingest_uploads(config.CHROMA_VAULT_DIR)
    except Exception:
        log.exception("Startup indexing failed; continuing without re-indexing")

# Uploaded documents live and are retrieved from the uploads folder; discard the
# legacy-only collection after its documents have been migrated successfully.
chroma_client.get_or_create_collection(name=config.CHROMA_COLLECTION)
chroma_client.delete_collection(config.CHROMA_COLLECTION)
chroma_client.get_or_create_collection(name=config.CHROMA_COLLECTION)

app = FastAPI(title="Math AI App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # Unhandled errors are answered outside CORSMiddleware, so they'd have no CORS headers and the page
    # would only see "Failed to fetch". Add them here so the real message gets through.
    logging.getLogger(__name__).exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error - check the backend logs"},
        headers={"Access-Control-Allow-Origin": request.headers.get("origin", "*")},
    )

app.include_router(auth_routes.router)
app.include_router(approval_routes.router)
app.include_router(user_routes.router)
app.include_router(teacher_routes.router)
app.include_router(materials_routes.router)
app.include_router(profile_routes.router)
app.include_router(subjects_routes.router)
app.include_router(subject_deletion_routes.router)
app.include_router(notification_routes.router)
app.include_router(learning_routes.router)
app.include_router(schools_routes.router)
app.include_router(school_admin_routes.router)
app.include_router(practice_routes.router)

@app.get("/")
def root():
    return {"message": "Math AI App is running", "storage": drive_storage.backend_name()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)