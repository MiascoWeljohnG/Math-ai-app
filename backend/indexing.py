"""Background indexing of uploaded files.

Indexing (read every page, cut it into chunks, embed each chunk with Gemini) can take minutes for a big PDF,
far longer than a web request should wait. So an upload only SAVES the file and its database row (status
"indexing"); this module then does the slow part in a background thread, one file at a time, and flips the
row to "ready" or "failed" (with a reason the page shows, and a Retry button).

Because the row exists from the first second, a file can no longer be saved to storage and then vanish from
the list when the request dies half-way.
"""
import logging
import threading
from datetime import datetime
from pathlib import Path

import config
from database import SessionLocal
from models import Material

log = logging.getLogger(__name__)

READY, INDEXING, FAILED = "ready", "indexing", "failed"

_one_at_a_time = threading.Semaphore(1)   # files queue up: keeps memory low and Gemini's rate limit happy
_active: set[int] = set()                 # material ids queued or running in THIS process
_active_lock = threading.Lock()
_progress: dict[int, dict] = {}           # material id -> how far along its job is (phase, done, total)
_STARTED = datetime.utcnow()              # rows older than this and still "indexing" lost their job in a restart


def get_progress(material_id: int) -> dict | None:
    """What the page shows while a file is being read: {"phase": "queued" | "reading" | "embedding" | "waiting",
    "done": n, "total": n}. None when no job in this process is working on it."""
    info = _progress.get(material_id)
    return dict(info) if info else None


def start_indexing(material_id: int, contents: bytes | None = None) -> bool:
    """Queue one file for background indexing. `contents` is the file's bytes if the caller still has them;
    otherwise they are read back from storage. Returns False if it is already queued."""
    with _active_lock:
        if material_id in _active:
            return False
        _active.add(material_id)
    _progress[material_id] = {"phase": "queued"}
    threading.Thread(target=_run, args=(material_id, contents), name=f"index-{material_id}", daemon=True).start()
    return True


def _run(material_id: int, contents: bytes | None) -> None:
    try:
        with _one_at_a_time:
            _index(material_id, contents)
    except Exception:   # a bug here must never leave the row stuck on "indexing"
        log.exception("Indexing job %s crashed", material_id)
        _finish(material_id, FAILED, "Indexing crashed unexpectedly. Press Retry.")
    finally:
        _progress.pop(material_id, None)
        with _active_lock:
            _active.discard(material_id)


def _index(material_id: int, contents: bytes | None) -> None:
    import rag

    # Short database sessions only: indexing can take minutes, and a connection left open that long
    # (Supabase/Postgres) may be dropped by the server.
    db = SessionLocal()
    try:
        material = db.query(Material).filter(Material.id == material_id).first()
        if material is None:   # deleted before its turn came
            return
        source, branch, drive_file_id = material.filename, material.branch or "General", material.drive_file_id
    finally:
        db.close()

    try:
        log.info("Indexing %s ...", source)
        _progress[material_id] = {"phase": "reading"}
        rag.set_job_progress(lambda **info: _progress.__setitem__(material_id, info))
        rag.set_job_deadline(config.INDEX_JOB_MAX_MINUTES * 60)
        data = contents if contents is not None else _load_bytes(source, drive_file_id)
        chunks = rag.index_document(source, branch, data)
    except Exception as exc:
        log.exception("Indexing %s failed", source)
        _finish(material_id, FAILED, _explain(exc))
        return
    finally:
        rag.set_job_deadline(None)
        rag.set_job_progress(None)
    if _finish(material_id, READY, None):
        log.info("Indexed %s (%d chunks)", source, chunks)
    else:   # deleted while we were indexing it: don't leave its chunks behind
        rag.delete_material_chunks(source)


def _finish(material_id: int, status: str, error: str | None) -> bool:
    """Record the outcome. False when the row no longer exists (the file was deleted meanwhile)."""
    db = SessionLocal()
    try:
        material = db.query(Material).filter(Material.id == material_id).first()
        if material is None:
            return False
        material.index_status, material.index_error = status, error
        db.commit()
        return True
    except Exception:
        db.rollback()
        log.exception("Couldn't record the indexing result for material %s", material_id)
        return False
    finally:
        db.close()


def _load_bytes(filename: str, drive_file_id: str | None) -> bytes:
    if drive_file_id:
        import drive_storage
        return drive_storage.download_bytes(drive_file_id)
    vault = Path(config.CHROMA_VAULT_DIR).expanduser().resolve()
    target = (vault / filename).resolve()
    if vault not in target.parents or not target.is_file():
        raise FileNotFoundError("The original file is missing from the server. Delete this entry and upload it again.")
    return target.read_bytes()


def _explain(exc: Exception) -> str:
    """The sentence the page shows next to a failed file."""
    if isinstance(exc, (ValueError, FileNotFoundError, TimeoutError)):
        return str(exc)[:300]
    if type(exc).__name__ == "EmbeddingQuotaError":   # carries its own plain-language advice
        return str(exc)[:400]
    return f"Indexing failed: {str(exc)[:200]}"


def retry(material: Material, db) -> None:
    """Put a failed (or stuck) file back in the queue."""
    material.index_status, material.index_error = INDEXING, None
    db.commit()
    start_indexing(material.id)


_RESUMED_MARK = "Resumed after a server restart."


def resume_stale_jobs() -> None:
    """Run once at startup, BEFORE the search index is rebuilt. A restart (Render sleeping, a redeploy) kills
    background jobs, leaving rows on "indexing" with nobody working on them. Queue each one again ONCE: the
    file is read back from storage, so nothing needs uploading twice.

    If a file is found stale a second time, the server died while reading it again (usually out of memory on
    a big PDF). Re-queuing it would crash the server on every start, so it is marked failed instead and the
    teacher can press Retry (or upload the file in smaller parts)."""
    db = SessionLocal()
    try:
        stale = db.query(Material).filter(Material.index_status == INDEXING, Material.uploaded_at < _STARTED).all()
        ids = []
        for material in stale:
            if material.index_error == _RESUMED_MARK:
                material.index_status = FAILED
                material.index_error = ("The server stopped twice while reading this file, most likely because it ran out "
                                        "of memory. Upload it in smaller parts (for example 50 pages each), then Retry.")
                log.warning("Not resuming material %s again: it already crashed the server once", material.id)
            else:
                material.index_error = _RESUMED_MARK
                ids.append(material.id)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Couldn't look for unfinished indexing jobs")
        return
    finally:
        db.close()
    for material_id in ids:
        if start_indexing(material_id):
            log.info("Resuming interrupted indexing of material %s", material_id)
