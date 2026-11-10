from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import func
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from auth import require_staff, require_teacher
from database import get_db
from adaptive import level_counts
from school import in_school, shared_subjects, visible_subjects
from models import ACTIVE, Lesson, Material, QuizAttempt, Subject, SubjectDeletionRequest, User
import config
from classifier import AUTO, ingest_with_detection, preview_pages
from progress import progress_for_user
from routes.materials_routes import material_summary

router = APIRouter(prefix="/teacher", tags=["teacher"])


ONLINE_WINDOW = timedelta(minutes=15)   # same meaning as "active now" on the school admin overview


@router.get("/overview")
def teacher_overview(user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """The four tiles at the top of the teacher page. Files are only this teacher's own uploads; lessons and
    students are those of the teacher's own school (the school comes from the account, never the request)."""
    now = datetime.utcnow()

    # 1. Files this teacher uploaded, split by type (.doc counts with .docx; pptx/txt go to "other").
    uploads = db.query(Material.display_name, Material.uploaded_at).filter(Material.uploaded_by == user.username).all()
    kinds = {"pdf": 0, "docx": 0, "other": 0}
    for name, _ in uploads:
        ext = Path(name or "").suffix.lower().lstrip(".")
        kinds["docx" if ext in ("docx", "doc") else "pdf" if ext == "pdf" else "other"] += 1
    stamps = [uploaded_at for _, uploaded_at in uploads if uploaded_at]

    # 2 + 3. Lessons of the school's shared subjects: drafts wait for approval, published ones are live.
    lesson_rows = (
        db.query(Lesson.status, Lesson.created_by, Lesson.created_at, Lesson.subject_id)
        .join(Subject, Subject.id == Lesson.subject_id)
        .filter(shared_subjects(user))
        .all()
    )
    drafts = [row for row in lesson_rows if row.status == "draft"]
    published = [row for row in lesson_rows if row.status == "published"]
    draft_dates = [row.created_at for row in drafts if row.created_at]
    subject_ids = {sid for (sid,) in db.query(Subject.id).filter(shared_subjects(user)).all()}
    subjects = len(subject_ids)
    # Teachers can't delete a subject on their own: an admin has to approve. Until then its lessons are still live,
    # but at risk. (There is no request for a single lesson; those are deleted directly.)
    asked = {sid for (sid,) in db.query(SubjectDeletionRequest.subject_id)
             .filter(SubjectDeletionRequest.status == "pending").all()} & subject_ids

    # 4. Students of this school who can sign in.
    in_my_school = in_school(User.school_id, user.school_id)
    students = db.query(User.last_seen_at).filter(User.role == "user", User.status == ACTIVE, in_my_school).all()
    seen = [row.last_seen_at for row in students if row.last_seen_at]

    return {
        "files": {
            "total": len(uploads),
            **kinds,
            "this_week": sum(1 for stamp in stamps if stamp >= now - timedelta(days=7)),
            "latest": (max(stamps).isoformat() + "Z") if stamps else None,
        },
        "lessons": {
            "drafts": len(drafts),
            "my_drafts": sum(1 for row in drafts if row.created_by == user.username),
            "oldest_draft_days": (now - min(draft_dates)).days if draft_dates else 0,
            "published": len(published),
            "my_published": sum(1 for row in published if row.created_by == user.username),
            "deletion_requested": sum(1 for row in published if row.subject_id in asked),   # live lessons in subjects awaiting deletion
            "deletion_subjects": len(asked),
            "subjects": subjects,
        },
        "students": {
            "active": len(students),
            "online": sum(1 for stamp in seen if stamp >= now - ONLINE_WINDOW),
            "today": sum(1 for stamp in seen if stamp >= now - timedelta(hours=24)),
            "week": sum(1 for stamp in seen if stamp >= now - timedelta(days=7)),
            "window_minutes": int(ONLINE_WINDOW.total_seconds() // 60),
        },
    }


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
    return result


MAX_ATTEMPT_ROWS = 500


@router.get("/students/{username}/attempts")
def student_attempts(
    username: str,
    subject_id: Optional[int] = None,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Every quiz attempt one student made, newest first: the lesson, the score, pass or fail, the time taken and
    when. It backs the "View" button on the Student Scores table. Only students of the caller's own school, and
    only the school's shared branches (a student's personal subjects stay private, as in /learning/rankings).
    subject_id narrows it to one branch, the same filter the table above it uses."""
    student = db.query(User).filter(
        User.username == username, User.role == "user", in_school(User.school_id, user.school_id)).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    shared = {s.id: s.name for s in db.query(Subject).filter(shared_subjects(user))}
    if subject_id is not None and subject_id not in shared:
        raise HTTPException(status_code=404, detail="Subject not found")

    query = (
        db.query(QuizAttempt, Lesson.title, Lesson.subject_id)
        .join(Lesson, Lesson.id == QuizAttempt.lesson_id)
        .filter(QuizAttempt.user_id == student.id, Lesson.subject_id.in_(list(shared)))
    )
    if subject_id is not None:
        query = query.filter(Lesson.subject_id == subject_id)

    rows, tries = [], {}   # tries: lesson id -> how many attempts so far, counted oldest first so "attempt 2" means the second
    for attempt, lesson_title, lesson_subject in query.order_by(QuizAttempt.created_at.asc(), QuizAttempt.id.asc()):
        tries[attempt.lesson_id] = tries.get(attempt.lesson_id, 0) + 1
        rows.append({
            "id": attempt.id,
            "branch": shared[lesson_subject],
            "lesson": lesson_title,
            "attempt_no": tries[attempt.lesson_id],
            "score": attempt.score,
            "total": attempt.total,
            "percent": round(attempt.score * 100 / max(attempt.total, 1)),
            "passed": bool(attempt.passed),
            "seconds": attempt.seconds,
            "at": (attempt.created_at.isoformat() + "Z") if attempt.created_at else None,
        })
    rows.reverse()   # newest first

    return {
        "student": {"username": student.username, "name": student.display_name},
        "summary": {
            "attempts": len(rows),
            "passed": sum(1 for r in rows if r["passed"]),
            "average_percent": round(sum(r["percent"] for r in rows) / len(rows)) if rows else 0,
            "seconds": sum(r["seconds"] or 0 for r in rows),
        },
        "truncated": len(rows) > MAX_ATTEMPT_ROWS,
        "attempts": rows[:MAX_ATTEMPT_ROWS],
    }
