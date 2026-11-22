"""The archive. When a teacher deletes a file, a lesson or a subject it is not destroyed: it leaves the app at once (students
and the AI no longer see it) and a copy of what it was goes into `archived_items`. It stays there ARCHIVE_DAYS; once that has
passed it is listed on the school admin's File deletion page, and only the admin's "Delete permanently" removes it for good.

Archiving reuses the app's own delete code (delete_lesson_cascade, delete_subject_cascade, the Drive "Archived" folder), so
nothing else in the app has to know an archive exists. Every function here only adds to the session: the caller commits.
Everything is tied to a school, and each function is handed rows that were already checked to belong to the teacher's school."""
import json
import logging
import math
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import config
import drive_storage
from models import ArchivedItem, AuditLog, Lesson, LessonQuiz, Material, Subject, WeeklySchedule
from school import school_name

log = logging.getLogger(__name__)

ARCHIVE_DAYS = 30
RETENTION = timedelta(days=ARCHIVE_DAYS)
FILE, LESSON, SUBJECT = "file", "lesson", "subject"
KINDS = (FILE, LESSON, SUBJECT)


# ---- when does an archived item expire? ----

def expires_at(item: ArchivedItem) -> datetime:
    return item.archived_at + RETENTION


def is_due(item: ArchivedItem, now: Optional[datetime] = None) -> bool:
    """True once the item has been in the archive for ARCHIVE_DAYS: it can now be deleted permanently."""
    return (now or datetime.utcnow()) >= expires_at(item)


def days_left(item: ArchivedItem, now: Optional[datetime] = None) -> int:
    """Whole days until it can be deleted permanently (rounded up, 0 once due)."""
    seconds = (expires_at(item) - (now or datetime.utcnow())).total_seconds()
    return max(0, math.ceil(seconds / 86400))


def due_count(db: Session, school_id: Optional[int]) -> int:
    """How many of the school's archived items are waiting for the admin's permanent deletion."""
    cutoff = datetime.utcnow() - RETENTION
    return db.query(ArchivedItem).filter(ArchivedItem.school_id == school_id, ArchivedItem.archived_at <= cutoff).count()


# ---- snapshots ----

def _plain(value):
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def _row(obj) -> dict:
    """One database row as a JSON-safe dict."""
    return {column.name: _plain(getattr(obj, column.name)) for column in obj.__table__.columns}


def _clean(reason: Optional[str]) -> Optional[str]:
    return (reason or "").strip() or None


def archive_lesson(db: Session, lesson: Lesson, subject: Subject, by: str, school_id: Optional[int], reason: Optional[str] = None) -> ArchivedItem:
    """Take a lesson (with its quiz) out of the app and keep a copy. Students' completion records and practice sets on it go,
    exactly as when a lesson is deleted."""
    from routes.subjects_routes import delete_lesson_cascade
    quiz = db.query(LessonQuiz).filter(LessonQuiz.lesson_id == lesson.id).first()
    item = ArchivedItem(
        kind=LESSON, school_id=school_id, title=lesson.title, context=subject.name, reason=_clean(reason), archived_by=by,
        payload=json.dumps({"subject": {"id": subject.id, "name": subject.name}, "lesson": _row(lesson), "quiz": _row(quiz) if quiz else None}),
    )
    db.add(item)
    delete_lesson_cascade(db, lesson)
    return item


def archive_subject(db: Session, subject: Subject, by: str, school_id: Optional[int], reason: Optional[str] = None) -> ArchivedItem:
    """Take a shared subject out of the app with all its lessons and quizzes and keep a copy."""
    from routes.subjects_routes import delete_subject_cascade
    lessons = db.query(Lesson).filter(Lesson.subject_id == subject.id).order_by(Lesson.order_index, Lesson.id).all()
    quizzes = db.query(LessonQuiz).filter(LessonQuiz.lesson_id.in_([l.id for l in lessons])).all() if lessons else []
    schedule = db.query(WeeklySchedule).filter(WeeklySchedule.subject_id == subject.id).first()
    count = len(lessons)
    item = ArchivedItem(
        kind=SUBJECT, school_id=school_id, title=subject.name, context=f"{count} lesson{'' if count == 1 else 's'}",
        reason=_clean(reason), archived_by=by,
        payload=json.dumps({
            "subject": _row(subject), "lessons": [_row(l) for l in lessons], "quizzes": [_row(q) for q in quizzes],
            "weekly_schedule": _row(schedule) if schedule else None,
        }),
    )
    db.add(item)
    delete_subject_cascade(db, subject)
    return item


def _archive_dir() -> Path:
    """Where the originals of locally stored files wait. Next to the uploads folder, never inside it: the AI re-indexes
    everything inside the uploads folder at start-up. (Files kept in Google Drive wait in the school's Archived folder.)"""
    return Path(config.CHROMA_VAULT_DIR).expanduser().resolve().parent / "archived_uploads"


def archive_material(db: Session, material: Material, by: str, school_id: Optional[int], reason: Optional[str] = None) -> ArchivedItem:
    """Take an uploaded file out of the app and keep it. The record and what the AI learned from the file are removed, so students'
    questions stop using it. The original is kept: moved to the school's Archived folder in Drive, or (local storage) to the
    archived_uploads folder. A Drive failure raises 502 before anything is touched, so the delete can simply be retried."""
    from rag import delete_material_chunks
    storage, local_path = "none", None
    if material.drive_file_id:
        try:
            drive_storage.archive_file(material.drive_file_id, school=school_name(db, material.school_id))
        except drive_storage.DriveStorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        storage = "drive"

    delete_material_chunks(material.filename)
    vault_dir = Path(config.CHROMA_VAULT_DIR).expanduser().resolve()
    target = (vault_dir / material.filename).resolve()
    if vault_dir in target.parents and target.is_file():   # never touch anything outside the uploads folder
        if storage != "drive":
            destination = _archive_dir() / material.filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(destination))
            storage, local_path = "local", material.filename
        else:   # the Drive copy is the original; the leftover local cache can go
            target.unlink()

    item = ArchivedItem(
        kind=FILE, school_id=school_id, title=material.display_name, context=material.branch, reason=_clean(reason), archived_by=by,
        payload=json.dumps({"material": _row(material), "storage": storage, "local_path": local_path}),
    )
    db.add(item)
    db.delete(material)
    return item


# ---- permanent deletion ----

def purge_item(db: Session, item: ArchivedItem, by: str) -> str:
    """Delete an archived item for good. A file's original is removed too: deleted from local storage, or moved to the Drive
    trash (Drive empties its trash after 30 days). A Drive failure raises 502 and leaves the item in the archive so it can be
    retried. Returns the title. Does not commit."""
    payload = json.loads(item.payload or "{}")
    if item.kind == FILE:
        drive_id = (payload.get("material") or {}).get("drive_file_id")
        if payload.get("storage") == "drive" and drive_id:
            try:
                drive_storage.delete_file(drive_id)
            except drive_storage.DriveStorageError as exc:
                raise HTTPException(status_code=502, detail=str(exc))
        if payload.get("local_path"):
            root = _archive_dir().resolve()
            copy = (root / payload["local_path"]).resolve()
            if root in copy.parents and copy.is_file():
                copy.unlink()
    title = item.title
    db.add(AuditLog(actor=by, school_id=item.school_id, action="archive.purge", target=f"{item.kind}: {title}"))
    db.delete(item)
    return title


def settle_old_requests(db: Session, kind: str, key: str, value) -> None:
    """Deletion requests made before the archive existed may still be waiting for a decision on something that has just been
    archived. Nothing is left to decide, so close them (the same thing the request lists do when the target is already gone)."""
    from models import FileDeletionRequest, LessonDeletionRequest, SubjectDeletionRequest
    model = {FILE: FileDeletionRequest, LESSON: LessonDeletionRequest, SUBJECT: SubjectDeletionRequest}[kind]
    open_statuses = ["pending", "pending_main_admin"]
    for row in db.query(model).filter(getattr(model, key) == value, model.status.in_(open_statuses)):
        row.status, row.resolved_at = "approved", datetime.utcnow()
