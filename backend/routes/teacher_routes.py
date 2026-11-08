from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from auth import require_teacher
from database import get_db
from adaptive import level_counts
from school import in_school, shared_subjects, visible_subjects
from audit import log_view
from models import ACTIVE, Lesson, Material, Subject, User
import config
from classifier import AUTO, ingest_with_detection, preview_pages
from progress import progress_for_user
from routes.materials_routes import material_summary

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/subjects")
def teacher_subjects(user=Depends(require_teacher), db: Session = Depends(get_db)):
    return [{"id": subject.id, "name": subject.name} for subject in db.query(Subject).filter(visible_subjects(user)).order_by(Subject.name).all()]


@router.post("/upload")
async def teacher_upload(
    files: list[UploadFile] = File(...),
    branch: str = Form(AUTO),
    branches: str = Form(""),
    user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    # Mirrors admin_routes.py's /admin/upload — teachers upload into the
    # same shared knowledge base admins manage, just through their own
    # endpoint so the two roles stay clearly separate in the API.
    # branch=Auto: the AI picks each file's branch and only asks when it isn't sure (classifier.py)
    return await ingest_with_detection(files, branch, branches, user.username, db, school_id=user.school_id, user=user)


@router.post("/preview-file")
async def preview_file(file: UploadFile = File(...), user: User = Depends(require_teacher)):
    """Reads a file the teacher just picked (nothing is saved) so the "View file" popup can show its pages."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="The file must have a filename")
    contents = await file.read()
    if len(contents) > config.MAX_ANALYZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File is too large (limit {config.MAX_ANALYZE_BYTES // 1024 // 1024} MB)")
    try:
        return {"filename": file.filename, **await run_in_threadpool(preview_pages, file.filename, contents)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Couldn't read this file: {exc}")


@router.get("/files")
def my_files(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """Only the files this teacher uploaded. The filter is here, not in the page, so a
    teacher can't read other uploaders' files by editing the front end. Admins see all of
    them in /admin/files."""
    rows = (
        db.query(Material)
        .filter(Material.uploaded_by == user.username)
        .order_by(Material.uploaded_at.desc(), Material.id.desc())
        .all()
    )
    return [material_summary(m) for m in rows]


@router.get("/students")
def list_students(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """The students of this teacher's school, each with their real progress per math branch.
    There's no per-class roster model yet, so a teacher sees every student of their own school."""
    students = db.query(User).filter(User.role == "user", User.status == ACTIVE, in_school(User.school_id, user.school_id)).all()
    # one column per shared subject, so branches the AI creates (or the admins delete) show up here
    branches = [name for (name,) in db.query(Subject.name).filter(shared_subjects(user)).order_by(Subject.id.asc())]
    empty = {"completed": 0, "total": 0, "percent": 0}
    # how many shared lessons each student is struggling with / has mastered (their private subjects stay private)
    lessons = [i for (i,) in db.query(Lesson.id).join(Subject, Subject.id == Lesson.subject_id).filter(shared_subjects(user))]
    levels = level_counts(db, [s.id for s in students], lessons)
    result = []
    for s in students:
        by_branch = {p["branch"]: p for p in progress_for_user(db, s) if not p["is_personal"]}
        result.append({
            "username": s.username,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "middle_name": s.middle_name,
            "email": s.email,
            # one entry per dashboard column, in the same order for every student
            "progress": [by_branch.get(b, {"branch": b, **empty}) for b in branches],
            "levels": levels[s.id],
        })
    log_view(db, user, "roster.view", detail=f"{len(result)} students")   # names and emails of students
    return result
