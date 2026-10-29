import json
import random
import re
import unicodedata
from fractions import Fraction
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

import config
from auth import get_current_user, require_staff
from database import get_db
from models import Lesson, LessonCompletion, LessonQuiz, Material, PracticeSet, QuizAttempt, Subject, User
from classifier import check_relevance, choose_subject, document_text, read_upload, relevant_text, sample_text, summarize_document
from rag import ask_stream, generate_text
from routes.materials_routes import material_bytes
from school import in_school, shared_subjects, visible_subjects

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _serialize_subject(subject: Subject) -> dict:
    return {
        "id": subject.id,
        "name": subject.name,
        "description": subject.description,
        "is_personal": subject.owner_user_id is not None,
    }


def _visible_subject_or_404(db: Session, subject_id: int, user: User) -> Subject:
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if subject is None or (subject.owner_user_id is not None and subject.owner_user_id != user.id):
        raise HTTPException(status_code=404, detail="Subject not found")
    if subject.owner_user_id is None and subject.school_id != user.school_id:   # another school's subject
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


def _shared_subject_or_404(db: Session, subject_id: int, user: User) -> Subject:
    subject = db.query(Subject).filter(Subject.id == subject_id, shared_subjects(user)).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.get("")
def list_subjects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subjects = (
        db.query(Subject)
        .filter(visible_subjects(user))
        .order_by(Subject.owner_user_id.is_(None).desc(), Subject.id.asc())
        .all()
    )
    return [_serialize_subject(subject) for subject in subjects]


class CreateSubjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)


@router.post("")
def create_personal_subject(
    req: CreateSubjectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Subject name is required")
    subject = Subject(
        name=name,
        description=(req.description or "").strip() or None,
        owner_user_id=user.id,
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return _serialize_subject(subject)


@router.post("/shared")
def create_shared_subject(
    req: CreateSubjectRequest,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """A new branch every student of the creator's school can see. Names are unique within a school (ignoring case)."""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Subject name is required")
    if db.query(Subject).filter(shared_subjects(user), func.lower(Subject.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail=f'A subject called "{name}" already exists')
    subject = Subject(name=name, description=(req.description or "").strip() or None, owner_user_id=None, school_id=user.school_id)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return _serialize_subject(subject)


@router.post("/suggest")
async def suggest_subject_from_file(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Reads an uploaded PDF/DOCX and proposes a name + description for a new personal subject.
    Nothing is saved: the student reviews the text and presses "Add subject" as usual."""
    _, text = await read_upload(file)
    try:
        name, description = await summarize_document(sample_text(text))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't generate a title and description: {exc}")
    return {"name": name, "description": description}


@router.delete("/{subject_id}")
def delete_personal_subject(
    subject_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    if subject.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own personal subjects")
    delete_subject_cascade(db, subject)
    db.commit()
    return {"message": "Subject deleted."}


def delete_subject_cascade(db: Session, subject: Subject) -> None:
    """Remove a subject with its lessons, quizzes and completion records. The caller commits.
    Also used by subject_deletion_routes once every admin has approved."""
    lesson_ids = [lesson.id for lesson in db.query(Lesson).filter(Lesson.subject_id == subject.id)]
    _delete_lesson_children(db, lesson_ids)
    db.query(Lesson).filter(Lesson.subject_id == subject.id).delete(synchronize_session=False)
    db.delete(subject)


def _delete_lesson_children(db: Session, lesson_ids: list[int]) -> None:
    if lesson_ids:
        db.query(LessonCompletion).filter(LessonCompletion.lesson_id.in_(lesson_ids)).delete(synchronize_session=False)
        db.query(LessonQuiz).filter(LessonQuiz.lesson_id.in_(lesson_ids)).delete(synchronize_session=False)
        db.query(PracticeSet).filter(PracticeSet.lesson_id.in_(lesson_ids)).delete(synchronize_session=False)


def _completed_ids(db: Session, user: User, lesson_ids: list[int]) -> set[int]:
    if not lesson_ids:
        return set()
    rows = db.query(LessonCompletion.lesson_id).filter(
        LessonCompletion.user_id == user.id,
        LessonCompletion.lesson_id.in_(lesson_ids),
    )
    return {lesson_id for (lesson_id,) in rows}


def _serialize_lesson(lesson: Lesson, include_content: bool = True, completed: bool = False) -> dict:
    result = {
        "id": lesson.id,
        "subject_id": lesson.subject_id,
        "title": lesson.title,
        "order_index": lesson.order_index,
        "created_by": lesson.created_by,
        "completed": completed,
    }
    if include_content:
        result["content"] = lesson.content
    return result


@router.get("/{subject_id}/lessons")
def list_lessons(
    subject_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _visible_subject_or_404(db, subject_id, user)
    lessons = (
        db.query(Lesson)
        .filter(Lesson.subject_id == subject_id)
        .order_by(Lesson.order_index.asc(), Lesson.id.asc())
        .all()
    )
    done = _completed_ids(db, user, [lesson.id for lesson in lessons])
    return [_serialize_lesson(lesson, include_content=False, completed=lesson.id in done) for lesson in lessons]


@router.get("/{subject_id}/lessons/{lesson_id}")
def get_lesson(
    subject_id: int,
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _visible_subject_or_404(db, subject_id, user)
    lesson = db.query(Lesson).filter(
        Lesson.id == lesson_id,
        Lesson.subject_id == subject_id,
    ).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return _serialize_lesson(lesson, completed=lesson.id in _completed_ids(db, user, [lesson.id]))


class CompletionRequest(BaseModel):
    completed: bool


@router.put("/{subject_id}/lessons/{lesson_id}/completion")
def set_lesson_completion(
    subject_id: int,
    lesson_id: int,
    req: CompletionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The "Mark as complete" button. Per student; this is what the progress bars count."""
    _visible_subject_or_404(db, subject_id, user)
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.subject_id == subject_id).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    row = db.query(LessonCompletion).filter(
        LessonCompletion.user_id == user.id,
        LessonCompletion.lesson_id == lesson_id,
    ).first()
    if req.completed and row is None:
        db.add(LessonCompletion(user_id=user.id, lesson_id=lesson_id))
    elif not req.completed and row is not None:
        db.delete(row)
    db.commit()
    return {"completed": req.completed}


class LessonRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)
    order_index: Optional[int] = Field(default=None, ge=0)


def _lesson_values(req: LessonRequest) -> tuple[str, str]:
    title = req.title.strip()
    content = req.content.strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="Lesson title and content are required")
    return title, content


@router.post("/{subject_id}/lessons")
def create_lesson(
    subject_id: int,
    req: LessonRequest,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    _shared_subject_or_404(db, subject_id, user)
    title, content = _lesson_values(req)
    lesson = Lesson(
        subject_id=subject_id,
        title=title,
        content=content,
        order_index=req.order_index or 0,
        created_by=user.username,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return _serialize_lesson(lesson)


@router.put("/{subject_id}/lessons/{lesson_id}")
def update_lesson(
    subject_id: int,
    lesson_id: int,
    req: LessonRequest,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    _shared_subject_or_404(db, subject_id, user)
    lesson = db.query(Lesson).filter(
        Lesson.id == lesson_id,
        Lesson.subject_id == subject_id,
    ).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    lesson.title, lesson.content = _lesson_values(req)
    if req.order_index is not None:
        lesson.order_index = req.order_index
    db.commit()
    db.refresh(lesson)
    return _serialize_lesson(lesson)


@router.delete("/{subject_id}/lessons/{lesson_id}")
def delete_lesson(
    subject_id: int,
    lesson_id: int,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    _shared_subject_or_404(db, subject_id, user)
    lesson = db.query(Lesson).filter(
        Lesson.id == lesson_id,
        Lesson.subject_id == subject_id,
    ).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    _delete_lesson_children(db, [lesson.id])
    db.delete(lesson)
    db.commit()
    return {"message": "Lesson deleted."}


class DraftLessonRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=160)


@router.post("/{subject_id}/lessons/draft")
async def draft_lesson(
    subject_id: int,
    req: DraftLessonRequest,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    subject = _shared_subject_or_404(db, subject_id, user)
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Lesson topic is required")

    prompt = (
        f'Write a short structured lesson on "{topic}" for the subject {subject.name}, '
        "aimed at a student who is new to the topic. Use markdown: a title, 2-4 short "
        "sections with headers, and at least one worked example. Keep it focused, not long."
    )
    async for event in ask_stream(prompt):
        if event["type"] == "done":
            if not event.get("answer", "").strip():
                raise HTTPException(status_code=502, detail="The model returned an empty lesson draft")
            return {"draft_content": event["answer"]}
        if event["type"] == "error":
            raise HTTPException(status_code=502, detail=event.get("detail", "Lesson draft failed"))
    raise HTTPException(status_code=502, detail="The model ended before returning a lesson draft")


# ---------------------------------------------------------------------------
# AI lesson generation
#   outline  -> a list of lesson titles for the subject
#   generate -> one full lesson, saved to the DB
# ---------------------------------------------------------------------------

LESSON_SYSTEM = (
    "You write lessons for a math learning app used by high-school students. "
    "Be accurate, friendly and clear. Never use emojis. Write math with LaTeX ($...$ inline, $$...$$ for display)."
)


def _writable_subject_or_404(db: Session, subject_id: int, user: User) -> Subject:
    """Shared subjects: teacher/admin only. Personal subjects: their owner."""
    subject = _visible_subject_or_404(db, subject_id, user)
    if subject.owner_user_id is None and user.role not in ("teacher", "school_admin"):
        raise HTTPException(status_code=403, detail="Teacher or admin access required")
    return subject


def _next_order(db: Session, subject_id: int) -> int:
    top = db.query(func.max(Lesson.order_index)).filter(Lesson.subject_id == subject_id).scalar()
    return (top or 0) + 1


class OutlineRequest(BaseModel):
    count: int = Field(default=6, ge=1, le=15)
    focus: Optional[str] = Field(default=None, max_length=200)


@router.post("/{subject_id}/lessons/outline")
async def outline_lessons(
    subject_id: int,
    req: OutlineRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subject = _writable_subject_or_404(db, subject_id, user)
    focus = f" Focus on: {req.focus.strip()}." if req.focus and req.focus.strip() else ""
    have = [lesson.title for lesson in db.query(Lesson).filter(Lesson.subject_id == subject_id)]
    skip = f" These lessons already exist, do not repeat them: {'; '.join(have)}." if have else ""
    prompt = (
        f"List {req.count} lesson titles that together teach {subject.name} to a beginner, "
        f"ordered so each lesson builds on the previous one.{focus}{skip} "
        "Output one title per line. No numbering, no bullets, no other text. "
        "Titles are plain text: no LaTeX and no dollar signs."
    )
    try:
        text = await generate_text(LESSON_SYSTEM, prompt, subject.name, subject.name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Outline generation failed: {exc}")
    return {"titles": _clean_titles(text)[: req.count]}


def _clean_titles(text: str) -> list[str]:
    titles = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", line).strip(" #*_`")
        if line:
            titles.append(line[:200])
    if not titles:
        raise HTTPException(status_code=502, detail="The model returned no lesson titles")
    return titles


@router.post("/{subject_id}/lessons/outline-from-file")
async def outline_lessons_from_file(
    subject_id: int,
    file: UploadFile = File(...),
    count: int = Form(5, ge=1, le=10),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lesson titles that together cover an uploaded PDF/DOCX, in the order it teaches them.
    The page then writes each one with /lessons/generate-from-file."""
    subject = _writable_subject_or_404(db, subject_id, user)
    _, text = await read_upload(file)
    prompt = (
        f"List {count} lesson titles that together teach the material in this document to a beginner, "
        "in the order the document teaches it, each one a specific topic from the document. "
        "Output one title per line. No numbering, no bullets, no other text. "
        "Titles are plain text: no LaTeX and no dollar signs.\n\n"
        f'Subject: {subject.name}\n\nDocument:\n"""\n{sample_text(text, 8000)}\n"""'
    )
    try:
        reply = await generate_text(LESSON_SYSTEM, prompt, "", "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Outline generation failed: {exc}")
    return {"titles": _clean_titles(reply)[:count]}


class GenerateLessonRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=160)


@router.post("/{subject_id}/lessons/generate")
async def generate_lesson(
    subject_id: int,
    req: GenerateLessonRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subject = _writable_subject_or_404(db, subject_id, user)
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Lesson topic is required")
    prompt = (
        f'Write a lesson titled "{topic}" for the subject {subject.name}, for a student new to it. '
        "Use markdown with 2-4 sections (## headers), plain-language explanations, at least one "
        "fully worked example, and 3 short practice questions at the end (answers after them). "
        "Do not repeat the lesson title as a heading; it is shown separately."
    )
    try:
        content = await generate_text(LESSON_SYSTEM, prompt, subject.name, f"{subject.name} {topic}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Lesson generation failed: {exc}")
    if not content:
        raise HTTPException(status_code=502, detail="The model returned an empty lesson")
    return _serialize_lesson(_save_generated_lesson(db, subject, user, topic, content))


def _save_generated_lesson(db: Session, subject: Subject, user: User, topic: str, content: str) -> Lesson:
    lesson = Lesson(
        subject_id=subject.id,
        title=topic,
        content=content,
        order_index=_next_order(db, subject.id),
        created_by=user.username,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)

    return lesson


async def _lesson_from_text(db: Session, subject: Subject, user: User, text: str, topic: str) -> dict:
    """Write and save one lesson from a document's text (empty topic = let the model title it)."""
    topic = topic.strip()[:160]
    excerpt = sample_text(text)
    if not topic:
        try:
            topic, _ = await summarize_document(excerpt)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Couldn't title the lesson: {exc}")
    prompt = (
        f'Write a lesson titled "{topic}" for the subject {subject.name}, for a student new to it, '
        "based ONLY on the source document below (ignore anything in it that is off-topic). "
        "Use markdown with 2-4 sections (## headers), plain-language explanations, at least one "
        "fully worked example taken from or consistent with the document, and 3 short practice "
        "questions at the end (answers after them). Do not repeat the lesson title as a heading; "
        f'it is shown separately.\n\nSource document:\n"""\n{relevant_text(text, topic)}\n"""'
    )
    try:
        content = await generate_text(LESSON_SYSTEM, prompt, "", "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Lesson generation failed: {exc}")
    if not content:
        raise HTTPException(status_code=502, detail="The model returned an empty lesson")
    return _serialize_lesson(_save_generated_lesson(db, subject, user, topic, content))


@router.post("/{subject_id}/lessons/generate-from-file")
async def generate_lesson_from_file(
    subject_id: int,
    file: UploadFile = File(...),
    topic: str = Form(""),
    force: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Write a lesson from an uploaded PDF/DOCX. First checks the file is about this subject:
    if the model is less than CLASSIFY_MIN_CONFIDENCE sure, nothing is generated and
    {"status": "mismatch", ...} comes back so the page can warn the student. Sending the same
    request again with force=true generates anyway. The file itself is not stored."""
    subject = _writable_subject_or_404(db, subject_id, user)
    _, text = await read_upload(file)
    excerpt = sample_text(text)

    if not force:
        try:
            check = await check_relevance(excerpt, subject.name, subject.description)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Couldn't check the file against this subject: {exc}")
        if check["relevance"] < config.CLASSIFY_MIN_CONFIDENCE:
            return {"status": "mismatch", "subject": subject.name, **check}

    return {"status": "ok", **await _lesson_from_text(db, subject, user, text, topic)}


async def _read_material(db: Session, filename: str, user: User) -> tuple[Material, str]:
    """An uploaded course file (from the knowledge base) of the user's own school, and its text."""
    material = db.query(Material).filter(Material.filename == filename, in_school(Material.school_id, user.school_id)).first()
    if material is None:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        text = await run_in_threadpool(lambda: document_text(Path(material.filename).name, material_bytes(material)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return material, text


class AnalyzeMaterialRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    count: int = Field(default=5, ge=1, le=10)


@router.post("/analyze-material")
async def analyze_material(
    req: AnalyzeMaterialRequest,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Step 1 of "generate lessons from an uploaded file". Saves nothing. Says which shared subject
    the file belongs to (status "existing"), that it is a new branch of math ("new", with the name to
    create), or that the model couldn't tell ("unclear"); plus the lesson titles it would write.
    The page then creates the subject if needed and calls /lessons/generate-from-material per title."""
    _, text = await _read_material(db, req.filename, user)
    shared = db.query(Subject).filter(shared_subjects(user)).order_by(Subject.id.asc()).all()
    try:
        choice = await choose_subject(sample_text(text), [(subject.name, subject.description) for subject in shared])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't work out which subject this file belongs to: {exc}")
    if choice["action"] == "not_math":
        return {"status": "not_math", "titles": []}

    subject = next((item for item in shared if item.name == choice["subject"]), None)
    have = [lesson.title for lesson in db.query(Lesson).filter(Lesson.subject_id == subject.id)] if subject else []
    skip = f" These lessons already exist, do not repeat them: {'; '.join(have)}." if have else ""
    prompt = (
        f"List {req.count} lesson titles that together teach the material in this document to a beginner, "
        "in the order the document teaches it, each one a specific topic from the document."
        f"{skip} Output one title per line. No numbering, no bullets, no other text. "
        "Titles are plain text: no LaTeX and no dollar signs.\n\n"
        f'Document:\n"""\n{sample_text(text, 8000)}\n"""'
    )
    try:
        titles = _clean_titles(await generate_text(LESSON_SYSTEM, prompt, "", ""))[: req.count]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Outline generation failed: {exc}")
    return {
        "status": choice["action"],
        "subject_id": subject.id if subject else None,
        "subject_name": subject.name if subject else choice["new_name"],
        "description": choice["description"],
        "confidence": round(choice["confidence"], 2),
        "titles": titles,
    }


class GenerateFromMaterialRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    topic: str = Field(default="", max_length=160)


@router.post("/{subject_id}/lessons/generate-from-material")
async def generate_lesson_from_material(
    subject_id: int,
    req: GenerateFromMaterialRequest,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Step 2: write one lesson for `topic` from a file already in the knowledge base."""
    subject = _shared_subject_or_404(db, subject_id, user)
    _, text = await _read_material(db, req.filename, user)
    return await _lesson_from_text(db, subject, user, text, req.topic)


# ---------------------------------------------------------------------------
# Quizzes: one AI-written quiz per lesson. Four question types:
#   mcq (multiple choice), tf (true/false), id (identification), num (exact number)
# The AI also rates how hard the topic is (1-5); that sets the time limit.
# Students never receive the answers: the quiz is graded here, on submit.
# ---------------------------------------------------------------------------

QUIZ_LENGTH = 10
MAX_VIOLATIONS = 5   # tab switches allowed before the page ends the quiz
PASS_PERCENT = 80    # score needed to move on to the next lesson
SECONDS_PER_QUESTION = {1: 30, 2: 45, 3: 60, 4: 75, 5: 90}   # by difficulty; edit to taste
QUIZ_TYPES = {"MCQ": "mcq", "TF": "tf", "ID": "id", "NUM": "num"}
QUIZ_FORMAT = (   # how the model must write questions; the quiz and the practice sets share it
    "Use ONLY this format, one blank line between questions, no other text:\n\n"
    "DIFFICULTY: 3\n\n"
    "TYPE: MCQ\nQ: question text\nA) choice\nB) choice\nC) choice\nD) choice\nANSWER: B\nWHY: one-sentence explanation\n\n"
    "TYPE: TF\nQ: a statement\nANSWER: True\nWHY: one-sentence explanation\n\n"
    "TYPE: ID\nQ: question text\nANSWER: constant term | constant | the constant term\nWHY: one-sentence explanation\n\n"
    "TYPE: NUM\nQ: question text\nANSWER: 12\nWHY: one-sentence explanation\n\n"
    "Rules: MCQ has exactly 4 choices, exactly one correct, no 'all of the above'. "
    "ID answers are 1-4 words. After ANSWER list EVERY wording a student could reasonably type, separated by | "
    "(the full term, the short form, common synonyms), because answers are matched exactly. "
    "NUM answers are one exact number (integer, decimal or a fraction like 3/4) with no units. "
    "A NUM question asks for that ONE number and nothing else: never also ask the student to convert, expand, "
    "rewrite or state an equation. Phrase it as one question, e.g. 'After expanding (x-4)(x+2)=0 into "
    "ax^2+bx+c=0, what is the value of b?'. Write math in LaTeX ($...$). "
    "Plain text and LaTeX only: no markdown such as ** or *; write emphasis in capitals (NOT).\n\n"
)
_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)(/\d+)?$")


def _lesson_in_subject_or_404(db: Session, subject_id: int, lesson_id: int) -> Lesson:
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.subject_id == subject_id).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


def _to_number(text) -> Optional[Fraction]:
    """'12', '-3.5', '3/4' -> an exact Fraction, so 0.75 and 3/4 match and 0.33 is not 1/3."""
    cleaned = unicodedata.normalize("NFKC", str(text)).replace("\u2212", "-").replace(",", "").replace(" ", "")
    cleaned = re.sub(r"^[A-Za-z]=", "", cleaned)   # "c = -10" and "x=3" count as -10 and 3
    # The whitelist also keeps exponents like 1e999999999 away from Fraction().
    if len(cleaned) > 40 or not _NUMBER_RE.match(cleaned):
        return None
    try:
        return Fraction(cleaned)
    except ZeroDivisionError:
        return None


def _tf_value(text) -> Optional[bool]:
    word = str(text).strip().strip("*.").lower()
    return True if word in ("true", "t") else False if word in ("false", "f") else None


def _norm_text(text) -> str:
    """Identification answers: ignore case, a leading a/an/the, spaces and trailing punctuation."""
    text = unicodedata.normalize("NFKC", str(text)).casefold().strip()
    text = re.sub(r"^(a|an|the)\s+", "", text)
    return re.sub(r"\s+", "", text).strip(".,;:!?")


# Words that don't change which term a student means: "constant" and "the constant term" are the same answer.
_FILLER_WORDS = {"a", "an", "the", "of", "is", "are", "its", "it", "called", "term", "terms"}


def _words(text) -> tuple:
    """Identification answers as comparable words: lower case, no punctuation, no filler words, singular.
    If nothing is left (the answer IS 'term'), keep every word so it can still be matched."""
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    words = re.findall(r"[^\W_]+", text)
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words]
    return tuple(w for w in words if w not in _FILLER_WORDS) or tuple(words)


def _id_matches(given: str, option: str) -> bool:
    """Flexible identification check: numbers match by value ('5' = '5.0' = 'c = 5'),
    text matches ignoring case, spacing, punctuation, articles and filler such as 'term'."""
    if _norm_text(given) == _norm_text(option):
        return True
    a, b = _to_number(given), _to_number(option)
    if a is not None or b is not None:
        return a is not None and a == b
    words = _words(given)
    return bool(words) and words == _words(option)


def _finish_question(cur: Optional[dict]) -> Optional[dict]:
    """Turn one parsed block into a stored question, or None if the model got it wrong."""
    if not cur or cur["answer"] is None:
        return None
    raw, kind = cur["answer"].strip(), cur["type"]
    if kind is None:   # model forgot TYPE: choices mean multiple choice, True/False means true/false
        kind = "mcq" if cur["choices"] else "tf" if _tf_value(raw) is not None else None
    question = {"type": kind, "question": cur["question"], "explanation": cur["explanation"]}
    if kind == "mcq":
        letter = re.match(r"\(?([A-D])\b", raw, re.I)
        if len(cur["choices"]) < 2 or not letter or ord(letter.group(1).upper()) - 65 >= len(cur["choices"]):
            return None
        correct = cur["choices"][ord(letter.group(1).upper()) - 65]
        random.shuffle(cur["choices"])  # models love putting the answer at B
        question.update(choices=cur["choices"], answer=cur["choices"].index(correct))
    elif kind == "tf":
        if _tf_value(raw) is None:
            return None
        question["answer"] = _tf_value(raw)
    elif kind == "id":
        if not raw:
            return None
        question["answer"] = raw   # "a | b" lists accepted alternatives
    elif kind == "num":
        if _to_number(raw) is None:
            return None
        question["answer"] = raw
    else:
        return None
    return question


def _parse_quiz(text: str) -> list[dict]:
    """Read the plain-text quiz format (TYPE: / Q: / A) B) C) D) / ANSWER: / WHY:).
    Plain text instead of JSON so LaTeX backslashes can't break parsing."""
    questions, cur, pending = [], None, None
    for raw in text.splitlines():
        line = raw.strip()
        if m := re.match(r"^\**TYPE\s*[:\-]\**\s*([A-Za-z]+)", line, re.I):
            if q := _finish_question(cur):
                questions.append(q)
            cur, pending = None, QUIZ_TYPES.get(m.group(1).upper())
        elif m := re.match(r"^\**Q\d*\s*[:.)]\**\s*(.+)", line, re.I):
            if q := _finish_question(cur):
                questions.append(q)
            cur = {"type": pending, "question": m.group(1).strip(), "choices": [], "answer": None, "explanation": ""}
            pending = None
        elif cur is None or not line:
            continue
        elif m := re.match(r"^\**([A-D])\s*[).:]\**\s*(.+)", line):
            cur["choices"].append(m.group(2).strip())
        elif m := re.match(r"^\**ANSWER\s*[:\-]\**\s*(.+)", line, re.I):
            cur["answer"] = m.group(1).strip()
        elif m := re.match(r"^\**WHY\s*[:\-]\**\s*(.+)", line, re.I):
            cur["explanation"] = m.group(1).strip()
        elif cur["answer"] is None and not cur["choices"]:
            cur["question"] += " " + line   # question text that wrapped onto a second line
    if q := _finish_question(cur):
        questions.append(q)
    return questions


def _parse_difficulty(text: str) -> int:
    m = re.search(r"DIFFICULTY\s*[:\-]\**\s*(\d)", text, re.I)
    return min(5, max(1, int(m.group(1)))) if m else 3


def _is_correct(question: dict, given) -> bool:
    kind, answer = question.get("type", "mcq"), question["answer"]   # quizzes saved before types existed are all mcq
    if given is None:
        return False
    if kind == "mcq":
        return isinstance(given, int) and not isinstance(given, bool) and given == answer
    if kind == "tf":
        return isinstance(given, bool) and given == answer
    given = str(given)[:200]
    if kind == "num":
        number = _to_number(given)
        return number is not None and number == _to_number(answer)
    return any(_id_matches(given, option) for option in str(answer).split("|") if option.strip())


def _display_answer(question: dict) -> str:
    kind, answer = question.get("type", "mcq"), question["answer"]
    if kind == "mcq":
        return question["choices"][answer]
    if kind == "tf":
        return "True" if answer else "False"
    return str(answer).split("|")[0].strip()


def _quiz_payload(db: Session, subject: Subject, lesson: Lesson, user: User, quiz: Optional[LessonQuiz]) -> dict:
    """Everything the quiz page needs. Answers are left out on purpose."""
    ids = [i for (i,) in db.query(Lesson.id).filter(Lesson.subject_id == subject.id)
           .order_by(Lesson.order_index.asc(), Lesson.id.asc())]
    position = ids.index(lesson.id)
    payload = {
        "subject": subject.name,
        "lesson_title": lesson.title,
        "lesson_number": position + 1,
        "next_lesson_id": ids[position + 1] if position + 1 < len(ids) else None,
        "can_regenerate": subject.owner_user_id is not None or user.role in ("teacher", "school_admin"),
        "quiz": None,
    }
    if quiz:
        stored = json.loads(quiz.questions)
        shown = []
        for i, q in enumerate(stored):
            item = {"id": i, "type": q.get("type", "mcq"), "question": q["question"]}
            if item["type"] == "mcq":
                item["choices"] = q["choices"]
            shown.append(item)
        random.shuffle(shown)   # a fresh order for every attempt
        difficulty = quiz.difficulty or 3
        payload["quiz"] = {
            "questions": shown,
            "difficulty": difficulty,
            "time_limit": len(shown) * SECONDS_PER_QUESTION[difficulty],
            "max_violations": MAX_VIOLATIONS,
            "pass_percent": PASS_PERCENT,
        }
    return payload


@router.get("/{subject_id}/lessons/{lesson_id}/quiz")
def get_quiz(
    subject_id: int,
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subject = _visible_subject_or_404(db, subject_id, user)
    lesson = _lesson_in_subject_or_404(db, subject_id, lesson_id)
    quiz = db.query(LessonQuiz).filter(LessonQuiz.lesson_id == lesson_id).first()
    return _quiz_payload(db, subject, lesson, user, quiz)


@router.post("/{subject_id}/lessons/{lesson_id}/quiz/generate")
async def generate_quiz(
    subject_id: int,
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Any student can generate the quiz the first time. Replacing an existing one is for
    teachers/admins (and a student's own personal subjects), so students can't keep re-rolling it."""
    subject = _visible_subject_or_404(db, subject_id, user)
    lesson = _lesson_in_subject_or_404(db, subject_id, lesson_id)
    can_replace = subject.owner_user_id is not None or user.role in ("teacher", "school_admin")
    quiz = db.query(LessonQuiz).filter(LessonQuiz.lesson_id == lesson_id).first()
    if quiz and not can_replace:
        return _quiz_payload(db, subject, lesson, user, quiz)

    prompt = (
        f'Write a {QUIZ_LENGTH}-question quiz on the lesson "{lesson.title}" ({subject.name}). '
        "The first line is DIFFICULTY: n, where n is 1 (very easy) to 5 (very hard) for a high-school student on this topic. "
        f"Then exactly {QUIZ_LENGTH} questions: 4 multiple choice (TYPE: MCQ), 2 true or false (TYPE: TF), "
        "2 identification (TYPE: ID), 2 numeric (TYPE: NUM). "
        + QUIZ_FORMAT +
        f"Lesson:\n{lesson.content[:6000]}"
    )
    questions, difficulty = [], 3
    for _ in range(2):  # small local models sometimes break the format; try once more
        try:
            text = await generate_text(LESSON_SYSTEM, prompt, "", "")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Quiz generation failed: {exc}")
        parsed = _parse_quiz(text)
        if len(parsed) > len(questions):
            questions, difficulty = parsed, _parse_difficulty(text)
        if len(questions) >= QUIZ_LENGTH // 2:
            break
    if len(questions) < QUIZ_LENGTH // 2:
        raise HTTPException(status_code=502, detail="The model's quiz could not be read. Please try again.")
    questions = questions[:QUIZ_LENGTH]

    quiz = db.query(LessonQuiz).filter(LessonQuiz.lesson_id == lesson_id).first()   # may have appeared while we waited
    if quiz and not can_replace:
        return _quiz_payload(db, subject, lesson, user, quiz)
    if quiz is None:
        quiz = LessonQuiz(lesson_id=lesson_id, questions="[]")
        db.add(quiz)
    quiz.questions = json.dumps(questions)
    quiz.difficulty = difficulty
    db.commit()
    return _quiz_payload(db, subject, lesson, user, quiz)


class SubmitQuizRequest(BaseModel):
    # question id -> mcq: choice index, tf: true/false, id/num: the typed text
    answers: dict[str, Optional[Union[bool, int, str]]] = Field(default_factory=dict)
    seconds: Optional[int] = Field(default=None, ge=0, le=86_400)   # how long the student took (browser clock)


@router.post("/{subject_id}/lessons/{lesson_id}/quiz/submit")
def submit_quiz(
    subject_id: int,
    lesson_id: int,
    req: SubmitQuizRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _visible_subject_or_404(db, subject_id, user)
    _lesson_in_subject_or_404(db, subject_id, lesson_id)
    quiz = db.query(LessonQuiz).filter(LessonQuiz.lesson_id == lesson_id).first()
    if quiz is None:
        raise HTTPException(status_code=404, detail="This lesson has no quiz yet")
    results = []
    for i, question in enumerate(json.loads(quiz.questions)):
        results.append({
            "id": i,
            "correct": _is_correct(question, req.answers.get(str(i))),
            "correct_answer": _display_answer(question),
            "explanation": question.get("explanation", ""),
        })
    score = sum(r["correct"] for r in results)
    passed = score * 100 >= PASS_PERCENT * len(results)   # whole numbers, so exactly 80% passes
    recorded = user.role == "user"   # a teacher previewing a quiz must not land on the leaderboard
    if recorded:
        limit = len(results) * SECONDS_PER_QUESTION[quiz.difficulty or 3]
        db.add(QuizAttempt(
            user_id=user.id, lesson_id=lesson_id, score=score, total=len(results), passed=passed,
            # ponytail: the time comes from the browser, so it is only clamped, not proven. Upgrade: stamp the start server-side.
            seconds=None if req.seconds is None else min(req.seconds, limit + 30),
            missed=json.dumps([r["id"] for r in results if not r["correct"]]),
        ))
        db.commit()
    return {
        "score": score,
        "total": len(results),
        "passed": passed,
        "pass_percent": PASS_PERCENT,
        "recorded": recorded,
        "results": results,
    }


@router.post("/{subject_id}/lessons/{lesson_id}/quiz/breakdown")
async def quiz_breakdown(
    subject_id: int,
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """After a failed attempt the AI re-teaches each missed question step by step. The text is saved on
    the attempt, so reloading the page never calls the model again."""
    _visible_subject_or_404(db, subject_id, user)
    lesson = _lesson_in_subject_or_404(db, subject_id, lesson_id)
    attempt = (db.query(QuizAttempt)
               .filter(QuizAttempt.user_id == user.id, QuizAttempt.lesson_id == lesson_id)
               .order_by(QuizAttempt.id.desc()).first())
    if attempt is None:
        raise HTTPException(status_code=404, detail="There is no quiz attempt to explain yet")
    if attempt.passed:
        raise HTTPException(status_code=400, detail="That attempt passed, so there is nothing to re-teach")
    if attempt.breakdown:
        return {"breakdown": attempt.breakdown}

    quiz = db.query(LessonQuiz).filter(LessonQuiz.lesson_id == lesson_id).first()
    stored = json.loads(quiz.questions) if quiz else []
    # ponytail: if a teacher regenerates the quiz after this attempt, the saved indexes point at new questions.
    missed = [stored[i] for i in json.loads(attempt.missed) if i < len(stored)]
    blocks = []
    for n, q in enumerate(missed, 1):
        text = f"{n}. {q['question']}"
        if q.get("type", "mcq") == "mcq":
            text += " Choices: " + "; ".join(q["choices"])
        blocks.append(f"{text}\nCorrect answer: {_display_answer(q)}")
    prompt = (
        f'A student failed the quiz on "{lesson.title}". For EACH question below, explain in short numbered steps '
        "how to reach the correct answer, then name the most common mistake in one sentence. "
        "Use simple words and write math in LaTeX ($...$). No emoji. "
        "Finish with a two-sentence study tip for this lesson.\n\n" + "\n\n".join(blocks)
    )
    try:
        text = (await generate_text(LESSON_SYSTEM, prompt, "", "")).strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't write the breakdown: {exc}")
    if not text:
        raise HTTPException(status_code=502, detail="The model returned an empty breakdown. Please try again.")
    attempt.breakdown = text
    db.commit()
    return {"breakdown": text}


LEADERBOARD_SIZE = 10


def _display_name(person: User) -> str:
    return person.display_name


@router.get("/{subject_id}/lessons/{lesson_id}/quiz/leaderboard")
def quiz_leaderboard(
    subject_id: int,
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Each student's best attempt on this lesson: highest percentage first, then the fastest time."""
    _visible_subject_or_404(db, subject_id, user)
    _lesson_in_subject_or_404(db, subject_id, lesson_id)
    best: dict[int, tuple] = {}
    for attempt, student in (db.query(QuizAttempt, User).join(User, User.id == QuizAttempt.user_id)
                             .filter(QuizAttempt.lesson_id == lesson_id)):
        key = (-attempt.score / max(attempt.total, 1), attempt.seconds if attempt.seconds is not None else 10**9)
        if student.id not in best or key < best[student.id][0]:
            best[student.id] = (key, attempt, student)
    ranked = sorted(best.values(), key=lambda row: row[0])[:LEADERBOARD_SIZE]
    return {"entries": [
        {
            "rank": rank,
            "name": _display_name(student),
            "score": attempt.score,
            "total": attempt.total,
            "seconds": attempt.seconds,
            "you": student.id == user.id,
        }
        for rank, (_, attempt, student) in enumerate(ranked, 1)
    ]}
