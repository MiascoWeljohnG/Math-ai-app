from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from pathlib import Path
from pydantic import BaseModel

from auth import require_admin, hash_password
from database import get_db
from models import User, UsageLog, Material
from rag import ingest_documents
from progress import UPLOAD_BRANCHES
import config
import uuid

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    branch: str = Form("General"),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
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

    # ingest_documents() is blocking (text extraction + Ollama embedding
    # calls). Running it inline here would freeze the event loop for every
    # other user — students' /ask requests would hang until the upload
    # finished. run_in_threadpool moves it off the event loop entirely.
    await run_in_threadpool(ingest_documents, saved_paths, branch)
    return {"message": f"Ingested {len(saved_paths)} file(s) under {branch}."}

@router.get("/users")
def list_users(user=Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "middle_name": u.middle_name,
            "email": u.email,
            "birthday": u.birthday,
            "role": u.role,
            "created": str(u.created_at),
        }
        for u in users
    ]

@router.get("/files")
def list_files(user=Depends(require_admin)):
    upload_dir = Path("./uploads")
    if not upload_dir.exists():
        return []
    files = [f.name for f in upload_dir.iterdir() if f.is_file()]
    return files

@router.delete("/knowledge-base")
def clear_knowledge_base(user=Depends(require_admin), db: Session = Depends(get_db)):
    """Wipes the vector store, the uploaded files on disk, and their branch
    records together, so the materials list and the AI's searchable content
    can never disagree about what exists."""
    import chromadb
    client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
    try:
        client.delete_collection(config.CHROMA_COLLECTION)
    except Exception:
        pass

    upload_dir = Path("./uploads")
    if upload_dir.exists():
        for f in upload_dir.iterdir():
            if f.is_file():
                f.unlink()
    db.query(Material).delete()
    db.commit()
    return {"message": "Knowledge base cleared. Re-upload your documents."}


class CreateTeacherRequest(BaseModel):
    username: str
    first_name: str
    last_name: str
    email: str
    password: str


@router.post("/create-teacher")
def create_teacher(
    req: CreateTeacherRequest,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Teachers are never self-registered through the public /auth/register
    # form (that always creates role="user") — only an admin can grant
    # teacher access, so this is the one place a "teacher" role gets created.
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    teacher = User(
        username=req.username,
        first_name=req.first_name,
        last_name=req.last_name,
        middle_name="",
        email=req.email,
        birthday="",
        password_hash=hash_password(req.password),
        role="teacher",
    )
    db.add(teacher)
    db.commit()
    return {"message": f"Teacher account '{req.username}' created."}   