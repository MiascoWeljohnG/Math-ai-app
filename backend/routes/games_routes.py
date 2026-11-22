"""Game packs. The Games page (games.html) plays word and concept games built from a lesson: hangman, word search,
matching, sorting, fill in the blanks. This route asks the model to turn one lesson into the content those games need.

Games are ungraded, like practice sets: nothing here touches the leaderboard, quiz attempts or the student's level.
XP and streaks live in the browser (see frontend/js/games-core.js).

The page works without this route (it falls back to words it finds in the lesson text), so a model error is harmless.
"""
import ast
import json
import operator
import re
from fractions import Fraction

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import get_current_user, require_staff
from database import get_db
from models import Lesson, User
from pydantic import BaseModel, Field
from rag import generate_text
from routes.subjects_routes import (
    GAME_PARTS, _lesson_in_subject_or_404, _require_unlocked, _shared_subject_or_404, _visible_subject_or_404, lesson_game_key,
)

router = APIRouter(prefix="/subjects", tags=["games"])

GAME_SYSTEM = (
    "You turn a math lesson into short game content for high-school students. Be accurate: every calculation must be right. "
    "Reply with ONE JSON object and nothing else: no markdown fences, no commentary. "
    "Use plain text only: no LaTeX, no backslashes, no dollar signs, no emojis. "
    "Write fractions as 3/4, powers as x^2 and multiplication with the word x or the sign *."
)

ALL_PARTS = ("terms", "sort", "blanks", "match", "problems")   # everything, for free play on a lesson that has no game of its own

# For each part of the content: its place in the JSON the model returns, and the rules it must follow.
PART_SPEC = {
    "terms": (
        '"terms": [{"word": "NUMERATOR", "clue": "The top number of a fraction"}]',
        '- "terms": exactly 8 important vocabulary words from the lesson. "word" is ONE word, letters A-Z only, 4 to 10 letters.\n'
        '  "clue" is a hint under 100 characters that does NOT contain the word itself.',
    ),
    "sort": (
        '"sort": {"left": "Name of group 1", "right": "Name of group 2",\n'
        '            "items": [{"text": "short item", "side": "left"}, {"text": "short item", "side": "right"}]}',
        '- "sort": two clearly different groups from the lesson (for example "Even numbers" and "Odd numbers", or "True statements"\n'
        '  and "False statements"). Exactly 5 items for each group, each item under 40 characters, every item clearly belongs to one group.',
    ),
    "blanks": (
        '"blanks": [{"sentence": "A ___ is a number multiplied by itself.", "answer": "square"}]',
        '- "blanks": exactly 4 sentences taken or adapted from the lesson. Each has exactly one "___" blank. "answer" is 1 to 3 words\n'
        '  and is not found anywhere else in the sentence.',
    ),
    "match": (
        '"match": [{"a": "term", "b": "short definition"}]',
        '- "match": exactly 5 pairs. "a" is a term (under 25 characters), "b" is its definition (under 80 characters).',
    ),
    "problems": (
        '"problems": [{"question": "Solve for x: 2x + 3 = 11", "answer": "4", "wrong": ["3", "5", "7"], "steps": "Subtract 3 from both sides to get 2x = 8, then divide by 2."}]',
        '- "problems": exactly 6 problems where the student must CALCULATE or SOLVE something, never recall a definition. Base them on the\n'
        '  equations, formulas and worked examples in the lesson, with new numbers. Each "question" is under 90 characters and contains the\n'
        '  equation or calculation itself (for example "Solve for x: 3x - 5 = 16" or "Evaluate: 4 + 3 x 2"). "answer" is ONE short number,\n'
        '  fraction like 3/4, or expression under 12 characters, and it must be correct. "wrong" is 3 different wrong answers of the same kind\n'
        '  that come from common mistakes. "steps" is a worked solution under 140 characters.',
    ),
}


def build_prompt(subject, lesson: Lesson, parts) -> str:
    """The model is only asked for the `parts` of the content that the game being prepared needs."""
    shape = ",\n  ".join(PART_SPEC[part][0] for part in parts)
    rules = "\n".join(PART_SPEC[part][1] for part in parts)
    return (f"Lesson title: {lesson.title}\nSubject: {subject.name}\n\n"
            "Write game content from the lesson below. Reply with this JSON shape:\n\n"
            "{\n  " + shape + "\n}\n\nRules:\n" + rules + "\n\nLesson:\n" + (lesson.content or "")[:6000] + "\n")


def _game_or_400(game: Optional[str]) -> Optional[str]:
    game = (game or "").strip()
    if game and game not in GAME_PARTS:
        raise HTTPException(status_code=400, detail="Choose a valid game")
    return game or None


def _game_of(lesson: Lesson, asked: Optional[str]) -> Optional[str]:
    """The game to write content for: the one asked for, else the lesson's own game, else None (free play: every game)."""
    asked = _game_or_400(asked)
    if asked:
        return asked
    return lesson.preferred_game if lesson.preferred_game in GAME_PARTS else None


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


# ---- checking the model's maths: a wrong answer key is worse than no question ----
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _calc(node) -> Fraction:
    """Exact arithmetic on a parsed expression. Only numbers, + - * / ** and brackets are allowed."""
    if isinstance(node, ast.Expression):
        return _calc(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Fraction(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _calc(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left, right = _calc(node.left), _calc(node.right)
        if isinstance(node.op, ast.Pow):
            if right.denominator != 1 or abs(right) > 8 or abs(left) > 1000:
                raise ValueError("power out of range")
            return left ** int(right)
        if type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](left, right)
    raise ValueError("unsupported")


def _evaluate(expr: str, var: Optional[str] = None, value: Optional[Fraction] = None) -> Fraction:
    expr = expr.replace("\u00d7", "*").replace("\u00f7", "/").replace("\u2212", "-").replace("^", "**")
    expr = re.sub(r"(?<=[0-9a-z)])\s+x\s+(?=[0-9(])", " * ", expr)    # "4 + 3 x 2": a lone x between numbers is a times sign
    if var:
        expr = re.sub(rf"(?<![A-Za-z]){var}(?![A-Za-z])", f"({value})", expr)
    expr = re.sub(r"(?<=[0-9)])\s*(?=\()", "*", expr)                  # 2(4) and )( mean multiply
    return _calc(ast.parse(expr.strip(), mode="eval"))


def check_problem(question: str, answer: str) -> Optional[bool]:
    """True or False when the answer can be verified by arithmetic, None when it cannot (word problems, formulas)."""
    try:
        want = Fraction(re.sub(r"^[a-z]\s*=\s*", "", answer.replace("\u2212", "-").replace(" ", "")))
        body = question.split(":", 1)[-1] if ":" in question else question
        body = re.sub(r"^(what is|calculate|evaluate|simplify|compute|find|solve( for [a-z])?)\s*", "", body.strip().rstrip("?."), flags=re.I)
        if not re.fullmatch(r"[0-9a-z+\-*/^().=\s\u00d7\u00f7\u2212]+", body.lower()):
            return None
        letters = set(re.findall(r"(?<![a-z])[a-z](?![a-z])", body.lower())) - ({"x"} if re.search(r"\d\s+x\s+\d", body) else set())
        if len(letters) > 1:
            return None
        var = next(iter(letters), None)
        if "=" in body:
            if body.count("=") != 1 or not var:
                return None
            left, right = body.split("=")
            return _evaluate(left, var, want) == _evaluate(right, var, want)
        if var:
            return None
        return _evaluate(body) == want
    except (ValueError, SyntaxError, ZeroDivisionError, ArithmeticError):
        return None


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

    problems = []
    for item in data.get("problems") or []:
        if not isinstance(item, dict):
            continue
        question, answer = _text(item.get("question"), 120), _text(item.get("answer"), 14)
        if not question or not answer or not re.search(r"\d", question) or check_problem(question, answer) is False:
            continue   # not a calculation, or the model's own answer fails when checked
        wrong, seen_answers = [], {answer.lower()}
        for value in item.get("wrong") or []:
            value = _text(value, 14)
            if value and value.lower() not in seen_answers:
                seen_answers.add(value.lower())
                wrong.append(value)
        problems.append({"question": question, "answer": answer, "wrong": wrong[:3], "steps": _text(item.get("steps"), 160)})
    if len(problems) >= 4:
        pack["problems"] = problems[:8]

    return pack


@router.post("/{subject_id}/lessons/{lesson_id}/games")
async def lesson_game_pack(
    subject_id: int, lesson_id: int,
    game: Optional[str] = Query(default=None, max_length=40),   # a lesson game id; empty means the lesson's own game
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The content for one lesson's game. Only the game the lesson is set to is written, never the others. A lesson with
    no game of its own (free play on the Games page) gets content for every game."""
    subject = _visible_subject_or_404(db, subject_id, user)
    lesson = _lesson_in_subject_or_404(db, subject_id, lesson_id)
    if lesson.status != "published" and user.role not in ("teacher", "school_admin"):
        raise HTTPException(status_code=404, detail="Lesson not found")
    _require_unlocked(db, subject, lesson, user)   # the same lock as the lesson itself
    game = _game_of(lesson, game)
    parts = GAME_PARTS[game] if game else ()

    key = lesson_game_key(lesson)
    if lesson.game_pack and lesson.game_pack_key == key:   # the version the teacher generated and can review
        try:
            stored = json.loads(lesson.game_pack)
        except ValueError:
            stored = None   # a damaged row: write a fresh pack below
        if isinstance(stored, dict) and stored and all(part in stored for part in parts):
            return stored
    cache_key = f"{key}:{game or 'all'}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    pack = await _write_pack(subject, lesson, game)
    _remember(cache_key, pack)
    return pack


def _remember(key: str, pack: dict) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = pack


async def _write_pack(subject, lesson: Lesson, game: Optional[str] = None) -> dict:
    """Asks the model for the game content of `game` only (or for every game when `game` is None). Raises a 502 when nothing
    usable comes back."""
    parts = GAME_PARTS[game] if game else ALL_PARTS
    prompt = build_prompt(subject, lesson, parts)
    pack: dict = {}
    for _ in range(2):   # small local models sometimes break the format; try once more
        try:
            text = await generate_text(GAME_SYSTEM, prompt, "", "")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Couldn't write the games: {exc}")
        candidate = {part: value for part, value in clean_pack(_extract_json(text)).items() if part in parts}   # never keep extras
        if len(candidate) > len(pack):
            pack = candidate
        if len(pack) >= (len(parts) if game else 3):
            break
    if not pack:
        raise HTTPException(status_code=502, detail="The model's game content could not be read. Please try again.")
    return pack


class GenerateGameRequest(BaseModel):
    game_id: str = Field(default="", max_length=40)   # the game to write content for; empty = the game the lesson is set to


@router.post("/{subject_id}/lessons/{lesson_id}/games/generate")
async def generate_lesson_game(
    subject_id: int, lesson_id: int, req: Optional[GenerateGameRequest] = None,
    user: User = Depends(require_staff), db: Session = Depends(get_db),
):
    """A teacher writes (or rewrites) the game content for a lesson's game and keeps it with the lesson. Only that game's
    content is written, not the other games'. Students then play exactly this version instead of waiting for the model.
    It goes stale when the lesson text changes."""
    subject = _shared_subject_or_404(db, subject_id, user)
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.subject_id == subject_id).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not (lesson.content or "").strip():
        raise HTTPException(status_code=400, detail="Write the lesson first, then generate its game.")
    game = _game_of(lesson, req.game_id if req else None)
    pack = await _write_pack(subject, lesson, game)
    key = lesson_game_key(lesson)
    lesson.game_pack, lesson.game_pack_key = json.dumps(pack), key
    db.commit()
    _remember(f"{key}:{game or 'all'}", pack)
    return {"pack": pack, "game_status": "ready", "game": game}


class LessonGameRequest(BaseModel):
    game_id: str = Field(default="", max_length=40)   # empty clears the lesson's game


_ALLOWED_GAMES = set(GAME_PARTS)


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
