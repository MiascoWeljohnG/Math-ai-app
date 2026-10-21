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
    Uploads files into the shared knowledge base. Handles AI quota/rate-limit (429) errors 
    gracefully by saving file metadata and storage links without immediate embedding generation,
    allowing batch uploads to complete. You can re-index them later from the dashboard.
    """
    try:
        return await ingest_with_detection(files, branch, branches, user.username, db, school_id=user.school_id)
    except Exception as e:
        error_msg = str(e).lower()
        # Check for AI rate limit, quota exhaustion (429), or general embedding failures
        if "429" in error_msg or "quota" in error_msg or "rate limit" in error_msg or "embedding" in error_msg:
            log.warning("AI embedding quota exceeded or failed during upload (429). Falling back to metadata-only save: %s", e)
            
            # Fallback: Save file records to the database and storage without running AI embeddings
            saved_names = []
            try:
                import drive_storage
                import config
                import os
                import io

                for file in files:
                    filename = file.filename
                    content = await file.read()
                    
                    drive_file_id = None
                    
                    # Try pushing to Google Drive if enabled
                    if drive_storage.enabled():
                        try:
                            from googleapiclient.http import MediaIoBaseUpload
                            file_stream = io.BytesIO(content)
                            folder_id = drive_storage.check()
                            media = MediaIoBaseUpload(file_stream, mimetype='application/pdf', resumable=True)
                            uploaded_drive_file = drive_storage.service.files().create(
                                body={'name': filename, 'parents': [folder_id]},
                                media_body=media,
                                fields='id, webViewLink'
                            ).execute()
                            drive_file_id = uploaded_drive_file.get('id')
                        except Exception as drive_err:
                            log.error("Drive upload failed during fallback for %s: %s", filename, drive_err)

                    # Fallback local save
                    local_path = os.path.join(config.CHROMA_VAULT_DIR, filename)
                    os.makedirs(config.CHROMA_VAULT_DIR, exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(content)

                    # Resolve branch value
                    assigned_branch = branch if branch != AUTO else "General"

                    # Save material record to PostgreSQL database
                    existing = db.query(Material).filter(Material.filename == filename, Material.uploaded_by == user.username).first()
                    if not existing:
                        mat = Material(
                            filename=filename,
                            display_name=filename,
                            branch=assigned_branch,
                            uploaded_by=user.username,
                            school_id=user.school_id,
                            drive_file_id=drive_file_id
                        )
                        db.add(mat)
                        db.commit()
                    
                    saved_names.append(filename)

                # Return full structure including empty lists to prevent frontend .map() errors
                return {
                    "message": f"Saved {len(saved_names)} file(s) successfully (AI indexing skipped due to token quota). Use 'Re-index' later.",
                    "saved_names": saved_names,
                    "savedNames": saved_names,
                    "unclassified": [],
                    "files": [],
                    "branches": []
                }

            except Exception as fallback_err:
                log.exception("Fallback save failed completely")
                raise HTTPException(status_code=500, detail=f"Upload and fallback failed: {str(fallback_err)}")

        # Re-raise any unrelated errors normally
        raise e


@router.get("/files")
def my_files(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """Only the files this teacher uploaded."""
    rows = (
        db.query(Material)
        .filter(Material.uploaded_by == user.username)
        .order_by(Material.uploaded_at.desc(), Material.id.desc())
        .all()
    )
    return [material_summary(m) for m in rows]


@router.get("/students")
def list_students(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """The students of this teacher's school, each with their real progress per math branch."""
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