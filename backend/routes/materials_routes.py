import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse

from auth import get_current_user
from database import get_db
from models import Material

router = APIRouter(prefix="/materials", tags=["materials"])

UPLOAD_DIR = Path("./uploads")


def _display_name(filename: str) -> str:
    # Uploads are saved on disk as "<32-char-hash>_<original-name>" (see
    # admin_routes.py) so two uploads of the same original filename never
    # collide. Strip that prefix for anything shown to a student.
    return re.sub(r"^[a-f0-9]{32}_", "", filename, flags=re.IGNORECASE)


@router.get("")
def list_materials(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Any logged-in user (student, teacher, or admin) can see what's in the
    shared knowledge base — this is the read-only view students use to
    browse what their teachers have uploaded. Files uploaded before branch
    tagging existed have no Material row, so they show up as "General"."""
    if not UPLOAD_DIR.exists():
        return []
    by_filename = {m.filename: m for m in db.query(Material).all()}
    result = []
    for f in sorted(UPLOAD_DIR.iterdir()):
        if not f.is_file():
            continue
        m = by_filename.get(f.name)
        result.append({
            "filename": f.name,
            "display_name": m.display_name if m else _display_name(f.name),
            "branch": m.branch if m else "General",
        })
    return result


@router.get("/{filename}/file")
def get_material_file(filename: str, user=Depends(get_current_user)):
    # Resolve the real path and confirm it's actually inside uploads/ before
    # serving it — without this check, a filename like "../../backend/config.py"
    # could be used to read arbitrary files off the server.
    target = (UPLOAD_DIR / filename).resolve()
    if UPLOAD_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=_display_name(filename))
