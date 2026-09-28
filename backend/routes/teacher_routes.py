from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth import require_teacher
from database import get_db
from models import User, Material
from rag import ingest_documents
from progress import progress_for_user, UPLOAD_BRANCHES

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.post("/upload")
async def teacher_upload(
    files: list[UploadFile] = File(...),
    branch: str = Form("General"),
    user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    # Mirrors admin_routes.py's /admin/upload — teachers upload into the
    # same shared knowledge base admins manage, just through their own
    # endpoint so the two roles stay clearly separate in the API. One branch
    # applies to every file in the batch.
    if branch not in UPLOAD_BRANCHES:
        raise HTTPException(status_code=400, detail=f"Branch must be one of: {', '.join(UPLOAD_BRANCHES)}")

    upload_dir = Path("./uploads")
    upload_dir.mkdir(exist_ok=True)

    saved_paths = []
    for file in files:
        safe_name = f"{uuid.uuid4().hex}_{file.filename}"
        path = upload_dir / safe_name
        path.write_bytes(await file.read())
        saved_paths.append(str(path))
        db.add(Material(
            filename=safe_name,
            display_name=file.filename,
            branch=branch,
            uploaded_by=user.username,
        ))
    db.commit()

    await run_in_threadpool(ingest_documents, saved_paths, branch)
    return {"message": f"Ingested {len(saved_paths)} file(s) under {branch}."}


@router.get("/students")
def list_students(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """All student accounts, each with their (currently mock) progress per
    math branch. There's no per-teacher class/roster model yet, so every
    teacher sees every student — narrow this query once that exists."""
    students = db.query(User).filter(User.role == "user").all()
    return [
        {
            "username": s.username,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "email": s.email,
            "progress": progress_for_user(s.username),
        }
        for s in students
    ]
