import asyncio
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from auth import get_current_user, require_teacher_or_admin
from database import get_db
from school import in_school
from models import Material
from rag import ingest_uploads
import config
import drive_storage

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


def material_bytes(material: Material) -> bytes:
    """The original file's bytes: from Google Drive when it was stored there, else from the uploads folder
    (files uploaded before Drive was switched on). Raises HTTPException, so routes can call it directly."""
    if material.drive_file_id:
        try:
            return drive_storage.download_bytes(material.drive_file_id)
        except drive_storage.DriveFileNotFound:
            raise HTTPException(status_code=404, detail="File not found - it was deleted from Google Drive")
        except drive_storage.DriveStorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    return _vault_material_path(material.filename).read_bytes()


@router.get("")
def list_materials(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """List uploaded originals stored in the uploads folder."""
    materials = db.query(Material).filter(in_school(Material.school_id, user.school_id)).order_by(Material.id.asc()).all()
    result = []
    for material in materials:
        if not material.drive_file_id:   # Drive files are trusted to exist; checking each would cost an API call per row
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
    name = material.display_name or _display_name(material.filename)
    if material.drive_file_id:
        return Response(
            content=material_bytes(material),
            media_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
        )
    return FileResponse(_vault_material_path(material.filename), filename=name)


@router.post("/reindex")
async def reindex_vault(user=Depends(require_teacher_or_admin), db: Session = Depends(get_db)):
    """Re-read the uploaded files into the AI's knowledge base. With Google Drive storage that means
    downloading every file again and re-indexing it; with local storage, re-reading the uploads folder
    (files copied in by hand are otherwise only picked up when the backend restarts)."""
    if drive_storage.enabled():
        from rag import sync_drive_index
        rows = db.query(Material).filter(Material.drive_file_id.isnot(None)).all()
        files = [(m.filename, m.branch or "General", m.drive_file_id) for m in rows]
        result = await asyncio.to_thread(sync_drive_index, files, True)
        if result["failed"] and not result["indexed_files"]:
            raise HTTPException(status_code=502, detail="Couldn't read the files from Google Drive. Check the backend logs.")
        return result   # includes "chunks", which the page shows
    try:
        chunks = await asyncio.to_thread(ingest_uploads, config.CHROMA_VAULT_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"chunks": chunks}
