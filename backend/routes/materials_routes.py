import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from auth import get_current_user, require_teacher_or_admin
from database import get_db
from school import in_school
from models import Material
from rag import ingest_uploads
import config

router = APIRouter(prefix="/materials", tags=["materials"])


def _display_name(filename: str) -> str:
    stored_name = Path(filename.replace("\\", "/")).name
    return re.sub(r"^[a-f0-9]{32}_", "", stored_name, flags=re.IGNORECASE)


def material_summary(material: Material) -> dict:
    """One uploaded file as the teacher and admin file tables show it."""
    uploaded = material.uploaded_at
    return {
        "filename": material.filename,
        "display_name": material.display_name or _display_name(material.filename),
        "branch": material.branch or "General",
        "uploaded_by": material.uploaded_by,
        # stored as UTC; the trailing Z makes the browser show the viewer's local time
        "uploaded_at": uploaded.isoformat() + "Z" if uploaded else None,
    }


def _vault_material_path(filename: str) -> Path:
    vault_dir = Path(config.CHROMA_VAULT_DIR).expanduser().resolve()
    target = (vault_dir / filename).resolve()
    if vault_dir not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return target


@router.get("")
def list_materials(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """List uploaded originals stored in the uploads folder."""
    materials = db.query(Material).filter(in_school(Material.school_id, user.school_id)).order_by(Material.id.asc()).all()
    result = []
    for material in materials:
        try:
            _vault_material_path(material.filename)
        except HTTPException:
            continue
        result.append({
            "filename": material.filename,
            "display_name": material.display_name or _display_name(material.filename),
            "branch": material.branch or "General",
        })
    return result


@router.get("/{filename:path}/file")
def get_material_file(
    filename: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = db.query(Material).filter(Material.filename == filename).first()
    # the main admin may open any school's file (the admin page lists them all); everyone else only their school's
    if material is None or (user.role != "admin" and material.school_id != user.school_id):
        raise HTTPException(status_code=404, detail="File not found")
    target = _vault_material_path(material.filename)
    return FileResponse(
        target,
        filename=material.display_name or _display_name(material.filename),
    )


@router.post("/reindex")
async def reindex_vault(user=Depends(require_teacher_or_admin)):
    """Re-read the uploads folder into the AI's knowledge base (files copied in by hand
    are otherwise only picked up when the backend restarts)."""
    try:
        chunks = await asyncio.to_thread(ingest_uploads, config.CHROMA_VAULT_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"chunks": chunks}
