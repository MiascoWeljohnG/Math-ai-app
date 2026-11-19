"""Game packs. The Games page (games.html) plays word and concept games built from a lesson: hangman, word search,
matching, sorting, fill in the blanks. This route asks the model to turn one lesson into the content those games need.

Games are ungraded, like practice sets: nothing here touches the leaderboard, quiz attempts or the student's level.
XP and streaks live in the browser (see frontend/js/games-core.js).

The page works without this route (it falls back to words it finds in the lesson text), so a model error is harmless.
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, require_staff
from database import get_db
from models import Lesson, User
from pydantic import BaseModel, Field
from rag import generate_text
from routes.subjects_routes import (
    _lesson_in_subject_or_404, _require_unlocked, _shared_subject_or_404, _visible_subject_or_404, lesson_game_key,
)

router = APIRouter(prefix="/subjects", tags=["games"])

GAME_SYSTEM = (
    "You turn a math lesson into short game content for high-school students. Be accurate. "
    "Reply with ONE JSON object and nothing else: no markdown fences, no commentary. "
    "Use plain text only: no LaTeX, no backslashes, no dollar signs, no emojis. "
    "Write fractions as 3/4 and powers as x^2."
)

GAME_PROMPT = """Lesson title: {title}
Subject: {subject}

Write game content from the lesson below. Reply with this JSON shape:

{{
  "terms": [{{"word": "NUMERATOR", "clue": "The top number of a fraction"}}],
  "sort": {{"left": "Name of group 1", "right": "Name of group 2",
            "items": [{{"text": "short item", "side": "left"}}, {{"text": "short item", "side": "right"}}]}},
  "blanks": [{{"sentence": "A ___ is a number multiplied by itself.", "answer": "square"}}],
  "match": [{{"a": "term", "b": "short definition"}}]
}}

Rules:
- "terms": exactly 8 important vocabulary words from the lesson. "word" is ONE word, letters A-Z only, 4 to 10 letters.
  "clue" is a hint under 100 characters that does NOT contain the word itself.
- "sort": two clearly different groups from the lesson (for example "Even numbers" and "Odd numbers", or "True statements"
  and "False statements"). Exactly 5 items for each group, each item under 40 characters, every item clearly belongs to one group.
- "blanks": exactly 4 sentences taken or adapted from the lesson. Each has exactly one "___" blank. "answer" is 1 to 3 words
  and is not found anywhere else in the sentence.
- "match": exactly 5 pairs. "a" is a term (under 25 characters), "b" is its definition (under 80 characters).

Lesson:
{content}
"""

_CACHE: dict[str, dict] = {}   # one pack per lesson text; a fresh one is only written when the lesson changes
_CACHE_MAX = 200


def _extract_json(text: str):
    """The first {...} block in the model's reply, or None. Small models often wrap JSON in fences or chatter."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def _text(value, limit: int) -> str:
    return re.sub(r"[\\$]", "", re.sub(r"\s+", " ", str(value or ""))).strip()[:limit]


def clean_pack(data) -> dict:
    """Keep only what the games can really use. A part that comes out too small is left out, and the page fills it
    from the lesson text instead, so one bad part never spoils the whole pack."""
    if not isinstance(data, dict):
        return {}
    pack: dict = {}

    terms, seen = [], set()
    for item in data.get("terms") or []:
        if not isinstance(item, dict):
            continue
        word = re.sub(r"[^A-Za-z]", "", str(item.get("word", ""))).upper()
        clue = _text(item.get("clue"), 120)
        leaks = word.lower() in re.sub(r"[^a-z]", "", clue.lower())   # the clue must not give the word away, even split by spaces
        if 4 <= len(word) <= 10 and clue and word not in seen and not leaks:
            seen.add(word)
            terms.append({"word": word, "clue": clue})
    if len(terms) >= 4:
        pack["terms"] = terms[:10]

    sort = data.get("sort")
    if isinstance(sort, dict):
        left, right = _text(sort.get("left"), 40), _text(sort.get("right"), 40)
        items = []
        for item in sort.get("items") or []:
            if isinstance(item, dict) and item.get("side") in ("left", "right") and _text(item.get("text"), 40):
                items.append({"text": _text(item["text"], 40), "side": item["side"]})
        if left and right and left.lower() != right.lower() \
                and sum(i["side"] == "left" for i in items) >= 2 and sum(i["side"] == "right" for i in items) >= 2:
            pack["sort"] = {"left": left, "right": right, "items": items[:12]}

    blanks = []
    for item in data.get("blanks") or []:
        if not isinstance(item, dict):
            continue
        sentence, answer = _text(item.get("sentence"), 220), _text(item.get("answer"), 30)
        if sentence.count("___") == 1 and answer and len(answer.split()) <= 3 and answer.lower() not in sentence.lower():
            blanks.append({"sentence": sentence, "answer": answer})
    if len(blanks) >= 3:
        pack["blanks"] = blanks[:5]

    pairs = []
    for item in data.get("match") or []:
        if isinstance(item, dict) and _text(item.get("a"), 30) and _text(item.get("b"), 90):
            pairs.append({"a": _text(item["a"], 30), "b": _text(item["b"], 90)})
    if len(pairs) >= 4:
        pack["match"] = pairs[:6]

    return pack


@router.post("/{subject_id}/lessons/{lesson_id}/games")
async def lesson_game_pack(
    subject_id: int, lesson_id: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    subject = _visible_subject_or_404(db, subject_id, user)
    lesson = _lesson_in_subject_or_404(db, subject_id, lesson_id)
    if lesson.status != "published" and user.role not in ("teacher", "school_admin"):
        raise HTTPException(status_code=404, detail="Lesson not found")
    _require_unlocked(db, subject, lesson, user)   # the same lock as the lesson itself

    key = lesson_game_key(lesson)
    if lesson.game_pack and lesson.game_pack_key == key:   # the version the teacher generated and can review
        try:
            return json.loads(lesson.game_pack)
        except ValueError:
            pass   # a damaged row: write a fresh pack below
    if key in _CACHE:
        return _CACHE[key]
    pack = await _write_pack(subject, lesson)
    _remember(key, pack)
    return pack


def _remember(key: str, pack: dict) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = pack


async def _write_pack(subject, lesson: Lesson) -> dict:
    """Asks the model for the lesson's game content. Raises a 502 when nothing usable comes back."""
    prompt = GAME_PROMPT.format(title=lesson.title, subject=subject.name, content=(lesson.content or "")[:6000])
    pack: dict = {}
    for _ in range(2):   # small local models sometimes break the format; try once more
        try:
            text = await generate_text(GAME_SYSTEM, prompt, "", "")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Couldn't write the games: {exc}")
        candidate = clean_pack(_extract_json(text))
        if len(candidate) > len(pack):
            pack = candidate
        if len(pack) >= 3:
            break
    if not pack:
        raise HTTPException(status_code=502, detail="The model's game content could not be read. Please try again.")
    return pack


@router.post("/{subject_id}/lessons/{lesson_id}/games/generate")
async def generate_lesson_game(
    subject_id: int, lesson_id: int,
    user: User = Depends(require_staff), db: Session = Depends(get_db),
):
    """A teacher writes (or rewrites) the game content for a lesson and keeps it with the lesson. Students then play
    exactly this version instead of waiting for the model. It goes stale when the lesson text changes."""
    subject = _shared_subject_or_404(db, subject_id, user)
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.subject_id == subject_id).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not (lesson.content or "").strip():
        raise HTTPException(status_code=400, detail="Write the lesson first, then generate its game.")
    pack = await _write_pack(subject, lesson)
    key = lesson_game_key(lesson)
    lesson.game_pack, lesson.game_pack_key = json.dumps(pack), key
    db.commit()
    _remember(key, pack)
    return {"pack": pack, "game_status": "ready"}


class LessonGameRequest(BaseModel):
    game_id: str = Field(default="", max_length=40)   # empty clears the lesson's game


_ALLOWED_GAMES = {"hangman", "word-search", "matching", "sorting", "fill-blanks"}


@router.put("/{subject_id}/lessons/{lesson_id}/preferred-game")
def set_preferred_game(
    subject_id: int, lesson_id: int, req: LessonGameRequest,
    user: User = Depends(require_staff), db: Session = Depends(get_db),
):
    subject = _shared_subject_or_404(db, subject_id, user)
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.subject_id == subject_id).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    game_id = req.game_id.strip()
    if game_id and game_id not in _ALLOWED_GAMES:
        raise HTTPException(status_code=400, detail="Choose a valid game")
    lesson.preferred_game = game_id or None
    db.commit()
    return {"lesson_id": lesson.id, "preferred_game": lesson.preferred_game}
