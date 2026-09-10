from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from pathlib import Path

from auth import require_admin
from database import get_db
from models import User, UsageLog
from rag import ingest_documents
import config
import uuid

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    user=Depends(require_admin),
):
    upload_dir = Path("./uploads")
    upload_dir.mkdir(exist_ok=True)

    saved_paths = []
    for file in files:
        safe_name = f"{uuid.uuid4().hex}_{file.filename}"
        path = upload_dir / safe_name
        path.write_bytes(await file.read())
        saved_paths.append(str(path))

    # ingest_documents() is blocking (text extraction + Ollama embedding
    # calls). Running it inline here would freeze the event loop for every
    # other user — students' /ask requests would hang until the upload
    # finished. run_in_threadpool moves it off the event loop entirely.
    await run_in_threadpool(ingest_documents, saved_paths)
    return {"message": f"Ingested {len(saved_paths)} file(s) into the knowledge base."}

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
def clear_knowledge_base(user=Depends(require_admin)):
    import chromadb
    client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
    try:
        client.delete_collection(config.CHROMA_COLLECTION)
    except Exception:
        pass
    return {"message": "Knowledge base cleared. Re-upload your documents."}   