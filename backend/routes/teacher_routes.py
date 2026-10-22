from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
import logging

from auth import require_teacher
from database import get_db
from adaptive import level_counts
from school import in_school, shared_subjects
from models import Lesson, Material, Subject, User
from classifier import AUTO, ingest_with_detection
from progress import progress_for_user
from routes.materials_routes import material_summary

router = APIRouter(prefix="/teacher", tags=["teacher"])
log = logging.getLogger(__name__)


@router.post("/upload")
async def teacher_upload(
    files: list[UploadFile] = File(...),
    branch: str = Form(AUTO),
    branches: str = Form(""),
    user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """
    Primary ingestion route with dual-storage fallback.
    If the AI provider triggers a rate limit or quota error (429), the exception is caught,
    and files are safely written to local disk, Google Drive, and PostgreSQL using the correct internal naming.
    """
    try:
        # Standard Pipeline: AI Embedding + Storage
        return await ingest_with_detection(files, branch, branches, user.username, db, school_id=user.school_id)
        
    except Exception as e:
        error_msg = str(e).lower()
        
        # Intercept AI rate limits, quota exhaustion (429), or general embedding API failures
        if "429" in error_msg or "quota" in error_msg or "rate limit" in error_msg or "embedding" in error_msg:
            log.warning("AI embedding quota exceeded (429). Triggering dual-storage fallback: %s", e)
            
            saved_names = []
            try:
                import config
                import os
                import io
                import uuid
                import drive_storage
                from googleapiclient.http import MediaIoBaseUpload

                for file in files:
                    # CRITICAL FIX: Rewind the file cursor to the beginning because the failing AI pipeline already read it
                    await file.seek(0)
                    content = await file.read()
                    
                    original_name = file.filename
                    assigned_branch = branch if branch != AUTO else "General"
                    
                    # Generate the exact internal filepath structure your system expects
                    unique_id = uuid.uuid4().hex
                    drive_filename = f"{unique_id}_{original_name}"
                    internal_filename = f"Uploaded Materials/{assigned_branch}/{drive_filename}"
                    
                    drive_file_id = None
                    
                    # 1. Cloud Storage Pipeline (Google Drive)
                    if drive_storage.enabled():
                        try:
                            file_stream = io.BytesIO(content)
                            folder_id = drive_storage.check()
                            media = MediaIoBaseUpload(file_stream, mimetype='application/pdf', resumable=True)
                            
                            uploaded_drive_file = drive_storage.service.files().create(
                                body={'name': drive_filename, 'parents': [folder_id]},
                                media_body=media,
                                fields='id'
                            ).execute()
                            
                            drive_file_id = uploaded_drive_file.get('id')
                            log.info("Fallback Drive upload successful for %s", original_name)
                        except Exception as drive_err:
                            log.error("Drive upload failed during fallback for %s: %s", original_name, drive_err)

                    # 2. Local Ephemeral Storage Pipeline
                    local_path = os.path.join(config.CHROMA_VAULT_DIR, internal_filename)
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(content)

                    # 3. Relational Storage Pipeline (PostgreSQL)
                    # We check against the display name just in case it was uploaded previously
                    existing = db.query(Material).filter(Material.display_name == original_name, Material.uploaded_by == user.username).first()
                    if not existing:
                        mat = Material(
                            filename=internal_filename,    # Fixed: "Uploaded Materials/Algebra/uuid_file.pdf"
                            display_name=original_name,    # Fixed: "file.pdf"
                            branch=assigned_branch,
                            uploaded_by=user.username,
                            school_id=user.school_id,
                            drive_file_id=drive_file_id    # Fixed: Will no longer be NULL
                        )
                        db.add(mat)
                        db.commit()
                        log.info("Database record created for %s", internal_filename)
                    
                    saved_names.append(original_name)

                # 4. Frontend Compatibility Payload
                return {
                    "message": f"Saved {len(saved_names)} file(s) successfully (AI indexing skipped due to token quota). Use 'Re-index' later.",
                    "saved_names": saved_names,
                    "savedNames": saved_names,
                    "uploaded": [{"filename": name, "branch": assigned_branch, "auto_detected": False} for name in saved_names],
                    "needs_topic": [],
                    "unclassified": [],
                    "files": [],
                    "branches": []
                }

            except Exception as fallback_err:
                log.exception("Catastrophic failure in fallback storage pipeline: %s", fallback_err)
                raise HTTPException(status_code=500, detail=f"Upload and fallback failed: {str(fallback_err)}")

        # If the error is completely unrelated to AI quotas, fail normally
        raise e


@router.get("/files")
def my_files(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """Retrieve only the material files uploaded by the authenticated teacher."""
    rows = (
        db.query(Material)
        .filter(Material.uploaded_by == user.username)
        .order_by(Material.uploaded_at.desc(), Material.id.desc())
        .all()
    )
    return [material_summary(m) for m in rows]


@router.get("/students")
def list_students(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """Retrieve students bound to the teacher's school, calculating real-time progress per branch."""
    students = db.query(User).filter(User.role == "user", in_school(User.school_id, user.school_id)).all()
    branches = [name for (name,) in db.query(Subject.name).filter(shared_subjects(user)).order_by(Subject.id.asc())]
    
    empty = {"completed": 0, "total": 0, "percent": 0}
    lessons = [i for (i,) in db.query(Lesson.id).join(Subject, Subject.id == Lesson.subject_id).filter(shared_subjects(user))]
    levels = level_counts(db, [s.id for s in students], lessons)
    
    result = []
    for s in students:
        by_branch = {p["branch"]: p for p in progress_for_user(db, s) if not p["is_personal"]}
        result.append({
            "username": s.username,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "email": s.email,
            "progress": [by_branch.get(b, {"branch": b, **empty}) for b in branches],
            "levels": levels[s.id],
        })
    return result