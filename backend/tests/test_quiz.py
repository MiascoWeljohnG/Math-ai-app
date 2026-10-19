"""Quiz parsing, grading and endpoints. The model is faked (see conftest.py)."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from database import get_db
from models import Lesson, LessonQuiz, Subject, User
from routes import subjects_routes as sr

QUIZ = """DIFFICULTY: 4

TYPE: MCQ
Q: Solve $2x + 6 = 18$.
A) 4
B) 5
C) 6
D) 8
ANSWER: C
WHY: Subtract 6 then divide by 2.

TYPE: TF
Q: A linear equation can have two different solutions.
ANSWER: False
WHY: A line crosses the x-axis once.

TYPE: ID
Q: What is the name of the formula for solving $ax^2+bx+c=0$?
ANSWER: quadratic formula | the quadratic formula
WHY: It is the standard name.

TYPE: NUM
Q: What is $3/4 + 1/2$?
ANSWER: 5/4
WHY: Common denominator 4.

TYPE: MCQ
Q: What is $3x = 12$ solved for x?
A) 3
B) 4
C) 9
D) 36
ANSWER: B
WHY: Divide both sides by 3.
"""


# ---------------------------------------------------------------- parsing
def test_parse_reads_all_four_types_and_difficulty():
    questions = sr._parse_quiz(QUIZ)
    assert [q["type"] for q in questions] == ["mcq", "tf", "id", "num", "mcq"]
    assert sr._parse_difficulty(QUIZ) == 4
    mcq = questions[0]
    assert mcq["choices"][mcq["answer"]] == "6"          # answer index follows the shuffle
    assert questions[1]["answer"] is False
    assert questions[3]["answer"] == "5/4"


def test_parse_drops_broken_questions_and_clamps_difficulty():
    text = "DIFFICULTY: 9\nTYPE: NUM\nQ: bad\nANSWER: twelve\nTYPE: TF\nQ: ok\nANSWER: True"
    assert [q["type"] for q in sr._parse_quiz(text)] == ["tf"]
    assert sr._parse_difficulty(text) == 5
    assert sr._parse_difficulty("no difficulty here") == 3


def test_parse_without_type_lines_falls_back_to_multiple_choice():
    text = "Q: 1+1?\nA) 1\nB) 2\nANSWER: B\nWHY: math"
    assert sr._parse_quiz(text)[0]["type"] == "mcq"


# ---------------------------------------------------------------- grading
@pytest.mark.parametrize("given, ok", [
    ("5/4", True), ("1.25", True), (" 1,25 ", False), ("1.250", True), ("\u22121.25", False),
    ("x = 1.25", True), ("c=5/4", True), ("c = ", False), ("= 1.25", False),
    ("1.2", False), ("", False), ("abc", False), ("1/0", False), ("1e999999999", False), (None, False),
])
def test_numeric_answers_must_be_exactly_right(given, ok):
    assert sr._is_correct({"type": "num", "answer": "5/4"}, given) is ok


def test_identification_ignores_case_articles_and_spacing_and_accepts_alternatives():
    q = {"type": "id", "answer": "quadratic formula | the quadratic formula"}
    assert sr._is_correct(q, "  The Quadratic   Formula. ")
    assert sr._is_correct(q, "quadratic formula")
    assert not sr._is_correct(q, "quadratic")


@pytest.mark.parametrize("given, ok", [
    ("constant", True), ("Constant Term", True), ("the constant", True), ("CONSTANT.", True), ("constants", True),
    ("term", False), ("linear term", False), ("coefficient", False), ("", False),
])
def test_identification_accepts_short_form_even_if_ai_listed_only_the_full_term(given, ok):
    assert sr._is_correct({"type": "id", "answer": "constant term"}, given) is ok


@pytest.mark.parametrize("given, ok", [("5", True), ("5.0", True), ("c = 5", True), ("-5", False), ("five", False)])
def test_identification_with_a_numeric_answer_matches_by_value(given, ok):
    assert sr._is_correct({"type": "id", "answer": "5"}, given) is ok


def test_true_false_and_multiple_choice_need_the_right_kind_of_value():
    assert sr._is_correct({"type": "tf", "answer": False}, False)
    assert not sr._is_correct({"type": "tf", "answer": True}, 1)     # 1 is not True
    assert sr._is_correct({"type": "mcq", "answer": 1, "choices": ["a", "b"]}, 1)
    assert not sr._is_correct({"type": "mcq", "answer": 1, "choices": ["a", "b"]}, True)
    assert sr._is_correct({"answer": 0, "choices": ["a", "b"]}, 0)   # quiz saved before types existed


# ---------------------------------------------------------------- endpoints
@pytest.fixture
def api(db, rag):
    student = User(username="stu", password_hash="x", role="user")
    other = User(username="stu2", password_hash="x", role="user")
    teacher = User(username="teach", password_hash="x", role="teacher")
    db.add_all([student, other, teacher])
    algebra = Subject(name="Algebra")
    db.add(algebra)
    db.commit()
    db.add_all([Lesson(subject_id=algebra.id, title=f"L{n}", content="x", order_index=n, created_by="teach") for n in (1, 2)])
    db.commit()
    app, current = FastAPI(), {"user": student}
    app.include_router(sr.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    client = TestClient(app)
    first, second = db.query(Lesson).order_by(Lesson.order_index).all()
    return types_namespace(client=client, current=current, rag=rag, db=db, base=f"/subjects/{algebra.id}/lessons/{first.id}/quiz",
                           student=student, other=other, teacher=teacher, second=second.id)


def types_namespace(**kwargs):
    import types
    return types.SimpleNamespace(**kwargs)


def test_student_generates_quiz_once_and_never_sees_answers(api):
    api.rag.reply = QUIZ
    assert api.client.get(api.base).json()["quiz"] is None
    body = api.client.post(f"{api.base}/generate").json()
    assert body["subject"] == "Algebra" and body["lesson_number"] == 1 and body["next_lesson_id"] == api.second
    quiz = body["quiz"]
    assert quiz["difficulty"] == 4 and quiz["time_limit"] == 5 * sr.SECONDS_PER_QUESTION[4]
    assert quiz["max_violations"] == sr.MAX_VIOLATIONS
    assert sorted(q["type"] for q in quiz["questions"]) == ["id", "mcq", "mcq", "num", "tf"]
    assert all("answer" not in q and "explanation" not in q for q in quiz["questions"])

    api.rag.reply = RuntimeError("must not be called")      # a second student click must not re-roll it
    assert api.client.post(f"{api.base}/generate").status_code == 200


def test_students_cannot_replace_a_quiz_but_teachers_can(api):
    api.rag.reply = QUIZ
    api.client.post(f"{api.base}/generate")
    api.current["user"] = api.teacher
    api.rag.reply = QUIZ.replace("DIFFICULTY: 4", "DIFFICULTY: 2")
    assert api.client.post(f"{api.base}/generate").json()["quiz"]["difficulty"] == 2


def test_unreadable_model_output_is_a_502_and_saves_nothing(api):
    api.rag.reply = "Sorry, I can't do that."
    assert api.client.post(f"{api.base}/generate").status_code == 502
    assert api.db.query(LessonQuiz).count() == 0


def test_submit_grades_on_the_server(api):
    api.rag.reply = QUIZ
    questions = api.client.post(f"{api.base}/generate").json()["quiz"]["questions"]
    stored = json.loads(api.db.query(LessonQuiz).one().questions)
    answers = {}
    for q in questions:
        truth = stored[q["id"]]["answer"]
        answers[str(q["id"])] = truth if q["type"] in ("mcq", "tf") else "1.25" if q["type"] == "num" else "Quadratic Formula"
    answers[str(next(q["id"] for q in questions if q["type"] == "tf"))] = True    # wrong on purpose
    out = api.client.post(f"{api.base}/submit", json={"answers": answers}).json()
    assert (out["score"], out["total"]) == (4, 5)
    assert out["passed"] is True and out["pass_percent"] == 80      # exactly 80% passes
    wrong = [r for r in out["results"] if not r["correct"]]
    assert len(wrong) == 1 and wrong[0]["correct_answer"] == "False"


def test_unanswered_questions_score_zero_and_missing_quiz_is_404(api):
    assert api.client.post(f"{api.base}/submit", json={"answers": {}}).status_code == 404
    api.rag.reply = QUIZ
    api.client.post(f"{api.base}/generate")
    out = api.client.post(f"{api.base}/submit", json={"answers": {}}).json()
    assert out["score"] == 0 and out["total"] == 5


def test_other_students_personal_subject_is_hidden(api):
    personal = Subject(name="Mine", owner_user_id=api.other.id)
    api.db.add(personal)
    api.db.commit()
    lesson = Lesson(subject_id=personal.id, title="P", content="x", created_by="stu2")
    api.db.add(lesson)
    api.db.commit()
    assert api.client.get(f"/subjects/{personal.id}/lessons/{lesson.id}/quiz").status_code == 404


def test_pass_mark_is_80_percent(api):
    api.rag.reply = QUIZ
    questions = api.client.post(f"{api.base}/generate").json()["quiz"]["questions"]
    stored = json.loads(api.db.query(LessonQuiz).one().questions)
    right = {"mcq": lambda a: a, "tf": lambda a: a, "id": lambda a: "quadratic formula", "num": lambda a: "5/4"}

    def score_with(wrong):
        answers = {str(q["id"]): right[q["type"]](stored[q["id"]]["answer"]) for q in questions}
        for q in questions[:wrong]:
            del answers[str(q["id"])]
        return api.client.post(f"{api.base}/submit", json={"answers": answers}).json()

    assert score_with(1)["passed"] is True       # 4 of 5
    assert score_with(2)["passed"] is False      # 3 of 5


def test_quiz_payload_tells_the_page_the_pass_mark(api):
    api.rag.reply = QUIZ
    assert api.client.post(f"{api.base}/generate").json()["quiz"]["pass_percent"] == 80


def test_prompt_asks_for_synonyms_and_single_number_answers(api):
    seen = []
    original = api.rag.generate_text

    async def spy(system, prompt, branch, query):
        seen.append(prompt)
        return QUIZ
    import sys
    sys.modules["rag"].generate_text = spy
    sr.generate_text = spy
    try:
        api.client.post(f"{api.base}/generate")
    finally:
        sys.modules["rag"].generate_text = original
        sr.generate_text = original
    assert "EVERY wording" in seen[0] and "ONE number and nothing else" in seen[0]
