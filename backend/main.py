import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, SessionLocal, migrate_add_missing_columns
from models import User, Subject
from auth import hash_password
from routes import auth_routes, admin_routes, user_routes, teacher_routes, materials_routes, profile_routes, subjects_routes, subject_deletion_routes, notification_routes, learning_routes, schools_routes, school_admin_routes, practice_routes
import config

Base.metadata.create_all(bind=engine)
migrate_add_missing_columns()

db = SessionLocal()
if not db.query(User).filter(User.username == "admin").first():
    db.add(User(
        username="admin",
        first_name="Admin",
        last_name="User",
        middle_name="",
        email="admin@mail.com",
        birthday="2000-01-01",
        password_hash=hash_password("admin123"),
        role="admin",
    ))
    db.commit()
# Seed the four default branches only on a brand-new database. Seeding "any that is missing" on every
# start would bring back a subject the admins just approved deleting.
if not db.query(Subject).filter(Subject.owner_user_id.is_(None)).first():
    for subject_name in ("Algebra", "Geometry", "Statistics", "Calculus"):
        db.add(Subject(name=subject_name))
db.commit()
db.close()

from rag import ingest_uploads, chroma_client

# Index the files in the uploads folder (the knowledge base)
ingest_uploads(config.CHROMA_VAULT_DIR)

# Uploaded documents live and are retrieved from the uploads folder; discard the
# legacy-only collection after its documents have been migrated successfully.
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

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
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
    return {"message": "Math AI App is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)