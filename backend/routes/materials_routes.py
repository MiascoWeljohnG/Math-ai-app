import asyncio
import io
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from auth import get_current_user, require_staff
import indexing
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
        # "indexing" (the AI is still reading it), "ready", or "failed" (index_error says why); rows from
        # before background indexing have no status and are ready
        "index_status": material.index_status or "ready",
        "index_error": material.index_error,
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
        if (material.index_status or "ready") != "ready":   # the AI can't use it yet (or at all)
            continue
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


@router.post("/{filename:path}/retry-index")
def retry_indexing(
    filename: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the AI's reading of a file again after it failed (or got stuck). The uploader or a school admin
    of the same school can do it; the file is not uploaded again."""
    material = db.query(Material).filter(Material.filename == filename).first()
    if material is None or material.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="File not found")
    if not (user.role == "school_admin" or (user.role == "teacher" and material.uploaded_by == user.username)):
        raise HTTPException(status_code=403, detail="Only the uploader or a school admin can retry this file")
    if material.index_status == indexing.INDEXING and material.id in indexing._active:
        return {"index_status": indexing.INDEXING}   # already running; nothing to do
    indexing.retry(material, db)
    return {"index_status": indexing.INDEXING}


@router.get("/{filename:path}/file")
def get_material_file(
    filename: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = db.query(Material).filter(Material.filename == filename).first()
    # only the user's own school's files
    if material is None or material.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="File not found")
    name = material.display_name or _display_name(material.filename)
    guessed_type = mimetypes.guess_type(name)[0]
    if not guessed_type and name.lower().endswith(".pptx"):
        guessed_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    media_type = guessed_type or "application/octet-stream"

    if material.drive_file_id:
        return Response(
            content=material_bytes(material),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
        )
    return FileResponse(_vault_material_path(material.filename), filename=name, media_type=media_type)


@router.get("/{filename:path}/slides")
def get_material_slides(
    filename: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = db.query(Material).filter(Material.filename == filename).first()
    if material is None or material.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="File not found")
    name = material.display_name or _display_name(material.filename)
    if not name.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only PowerPoint presentations (.pptx) have slide structures")
    
    raw = material_bytes(material)
    try:
        from pptx import Presentation
        prs = Presentation(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read presentation: {exc}")

    slides_data = []
    for i, slide in enumerate(prs.slides, 1):
        titles = []
        body_bullets = []
        tables = []
        notes = ""

        # Title shape
        if slide.shapes.title and slide.shapes.title.text:
            titles.append(slide.shapes.title.text.strip())

        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(r.text for r in para.runs).strip()
                    if line:
                        body_bullets.append(line)
            elif shape.has_table:
                tbl = []
                for row in shape.table.rows:
                    row_cells = [" ".join(cell.text.split()) for cell in row.cells]
                    tbl.append(row_cells)
                if tbl:
                    tables.append(tbl)

        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notes = slide.notes_slide.notes_text_frame.text.strip()

        slides_data.append({
            "slide_number": i,
            "title": " ".join(titles) if titles else f"Slide {i}",
            "bullets": body_bullets,
            "tables": tables,
            "notes": notes,
        })

    return {
        "filename": filename,
        "display_name": name,
        "total_slides": len(slides_data),
        "slides": slides_data,
    }


@router.post("/reindex")
async def reindex_vault(user=Depends(require_staff), db: Session = Depends(get_db)):
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
