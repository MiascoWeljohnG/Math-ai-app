"""Adaptive practice sets. After a weak quiz the AI writes an EASIER set on the ideas the student missed; after
a strong one it writes a HARDER challenge set. Which one is decided by adaptive.py from the quiz history.
Practice is ungraded: it never touches the leaderboard or the student's level."""
import json
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from adaptive import mastery_level, practice_kind
from auth import get_current_user
from database import get_db
from models import Lesson, LessonQuiz, PracticeSet, QuizAttempt, Subject, User
from rag import generate_text
from routes.subjects_routes import (
    LESSON_SYSTEM, QUIZ_FORMAT, _display_answer, _is_correct, _lesson_in_subject_or_404, _parse_quiz,
    _visible_subject_or_404,
)

router = APIRouter(prefix="/subjects", tags=["practice"])

PRACTICE_LENGTH = 5
PRACTICE_MIN = 3   # fewer readable questions than this and the model's answer is rejected


def _standing(db: Session, user: User, lesson_id: int):
    """(level, kind of practice offered, the student's latest attempt) from their quiz history on this lesson."""
    attempts = (db.query(QuizAttempt).filter(QuizAttempt.user_id == user.id, QuizAttempt.lesson_id == lesson_id)
                .order_by(QuizAttempt.id.asc()).all())
    best = max((round(a.score * 100 / max(a.total, 1)) for a in attempts), default=None)
    level = mastery_level(len(attempts), best, any(a.passed for a in attempts))
    return level, practice_kind(level), (attempts[-1] if attempts else None)


def _saved(db: Session, user: User, lesson_id: int, kind: Optional[str], latest: Optional[QuizAttempt]):
    """The stored set, but only if it was written for the student's latest attempt and the same kind."""
    if kind is None or latest is None:
        return None
    row = db.query(PracticeSet).filter(PracticeSet.user_id == user.id, PracticeSet.lesson_id == lesson_id).first()
    return row if row and row.kind == kind and row.attempt_id == latest.id else None


def _payload(subject: Subject, lesson: Lesson, level: str, kind: Optional[str], row: Optional[PracticeSet]) -> dict:
    """What the page needs. Answers are left out on purpose."""
    questions = None
    if row is not None:
        questions = []
        for i, q in enumerate(json.loads(row.questions)):
            item = {"id": i, "type": q.get("type", "mcq"), "question": q["question"]}
            if item["type"] == "mcq":
                item["choices"] = q["choices"]
            questions.append(item)
    return {"subject": subject.name, "lesson_title": lesson.title, "level": level, "kind": kind, "questions": questions}


@router.get("/{subject_id}/lessons/{lesson_id}/practice")
def get_practice(subject_id: int, lesson_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subject = _visible_subject_or_404(db, subject_id, user)
    lesson = _lesson_in_subject_or_404(db, subject_id, lesson_id)
    level, kind, latest = _standing(db, user, lesson_id)
    return _payload(subject, lesson, level, kind, _saved(db, user, lesson_id, kind, latest))


@router.post("/{subject_id}/lessons/{lesson_id}/practice/generate")
async def generate_practice(subject_id: int, lesson_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subject = _visible_subject_or_404(db, subject_id, user)
    lesson = _lesson_in_subject_or_404(db, subject_id, lesson_id)
    level, kind, latest = _standing(db, user, lesson_id)
    if kind is None:
        raise HTTPException(status_code=400, detail=(
            "Take this lesson's quiz first, then come back." if level == "new"
            else "You passed this lesson, so there is no extra practice set to do."))
    row = _saved(db, user, lesson_id, kind, latest)
    if row is not None:   # already written for this attempt: no second model call
        return _payload(subject, lesson, level, kind, row)

    quiz = db.query(LessonQuiz).filter(LessonQuiz.lesson_id == lesson_id).first()
    quiz_level = (quiz.difficulty if quiz else None) or 3
    if kind == "easier":
        stored = json.loads(quiz.questions) if quiz else []
        missed = [stored[i] for i in json.loads(latest.missed) if i < len(stored)][:PRACTICE_LENGTH]
        blocks = [f"{n}. {q['question']}\nCorrect answer: {_display_answer(q)}" for n, q in enumerate(missed, 1)]
        percent = round(latest.score * 100 / max(latest.total, 1))
        intro = (
            f'A student scored {percent}% on the quiz for the lesson "{lesson.title}" ({subject.name}) and missed these questions:\n'
            + "\n\n".join(blocks)
            + f"\n\nWrite a {PRACTICE_LENGTH}-question PRACTICE set on the SAME ideas that is EASIER than that quiz: "
            f"smaller numbers, one idea per question, simple wording. Use DIFFICULTY {max(1, quiz_level - 1)}. "
        )
    else:
        intro = (
            f'A student mastered the quiz for the lesson "{lesson.title}" ({subject.name}). '
            f"Write a {PRACTICE_LENGTH}-question CHALLENGE set that is HARDER than the quiz: multi-step problems "
            f"that combine the ideas. Use DIFFICULTY {min(5, quiz_level + 1)}. "
        )
    prompt = (
        intro + "The first line is DIFFICULTY: n. "
        f"Then exactly {PRACTICE_LENGTH} questions: 2 multiple choice (TYPE: MCQ), 1 true or false (TYPE: TF), "
        "1 identification (TYPE: ID), 1 numeric (TYPE: NUM). "
        + QUIZ_FORMAT + f"Lesson:\n{lesson.content[:6000]}"
    )
    questions: list = []
    for _ in range(2):   # small local models sometimes break the format; try once more
        try:
            text = await generate_text(LESSON_SYSTEM, prompt, "", "")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Couldn't write the practice set: {exc}")
        parsed = _parse_quiz(text)
        if len(parsed) > len(questions):
            questions = parsed
        if len(questions) >= PRACTICE_MIN:
            break
    if len(questions) < PRACTICE_MIN:
        raise HTTPException(status_code=502, detail="The model's practice set could not be read. Please try again.")

    row = db.query(PracticeSet).filter(PracticeSet.user_id == user.id, PracticeSet.lesson_id == lesson_id).first()
    if row is None:
        row = PracticeSet(user_id=user.id, lesson_id=lesson_id, kind=kind, questions="[]", attempt_id=latest.id)
        db.add(row)
    row.kind, row.questions, row.attempt_id = kind, json.dumps(questions[:PRACTICE_LENGTH]), latest.id
    db.commit()
    return _payload(subject, lesson, level, kind, row)


class SubmitPracticeRequest(BaseModel):
    # question id -> mcq: choice index, tf: true/false, id/num: the typed text (same as the quiz)
    answers: dict[str, Optional[Union[bool, int, str]]] = Field(default_factory=dict)


@router.post("/{subject_id}/lessons/{lesson_id}/practice/submit")
def submit_practice(
    subject_id: int, lesson_id: int, req: SubmitPracticeRequest,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _visible_subject_or_404(db, subject_id, user)
    _lesson_in_subject_or_404(db, subject_id, lesson_id)
    _, kind, latest = _standing(db, user, lesson_id)
    row = _saved(db, user, lesson_id, kind, latest)
    if row is None:
        raise HTTPException(status_code=404, detail="There is no practice set to check yet")
    results = [
        {"id": i, "correct": _is_correct(q, req.answers.get(str(i))), "correct_answer": _display_answer(q),
         "explanation": q.get("explanation", "")}
        for i, q in enumerate(json.loads(row.questions))
    ]
    return {"kind": kind, "score": sum(r["correct"] for r in results), "total": len(results), "results": results}
