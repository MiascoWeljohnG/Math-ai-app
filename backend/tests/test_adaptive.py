"""Adaptive learning: the mastery rules, the roadmap that follows them and the practice sets. The model is
faked (see conftest.py); the rules and the roadmap need no model at all."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adaptive import mastery_level, practice_kind
from auth import get_current_user
from database import get_db
from models import Lesson, PracticeSet, QuizAttempt, Subject, User
from routes import learning_routes, practice_routes, subjects_routes, teacher_routes
from test_quiz import QUIZ   # a model reply with 10 well-formed questions


# ---------------------------------------------------------------- the rules
@pytest.mark.parametrize("attempts, best, passed, level", [
    (0, None, False, "new"),
    (1, 70, False, "developing"),       # one near miss
    (1, 59, False, "struggling"),       # a weak first try
    (2, 79, False, "struggling"),       # still not through after two tries
    (1, 100, True, "mastered"),
    (2, 90, True, "mastered"),          # exactly 90% on the second try still counts
    (1, 85, True, "proficient"),        # passed, but under 90%
    (3, 100, True, "proficient"),       # needed three tries: passed, not mastered
])
def test_mastery_level_rules(attempts, best, passed, level):
    assert mastery_level(attempts, best, passed) == level


def test_which_practice_each_level_is_offered():
    assert [practice_kind(l) for l in ("new", "struggling", "developing", "proficient", "mastered")] == \
        [None, "easier", "easier", None, "harder"]


# ---------------------------------------------------------------- endpoints
@pytest.fixture
def api(db, rag):
    student = User(username="stu", password_hash="x", role="user", status="active")
    teacher = User(username="teach", password_hash="x", role="teacher")
    db.add_all([student, teacher, Subject(name="Algebra")])
    db.commit()
    subject = db.query(Subject).first()
    db.add_all(Lesson(subject_id=subject.id, title=f"L{n}", content="Solve equations.", order_index=n, created_by="teach") for n in (1, 2, 3))
    db.commit()
    lessons = db.query(Lesson).order_by(Lesson.order_index).all()
    app, current = FastAPI(), {"user": student}
    for module in (learning_routes, practice_routes, subjects_routes, teacher_routes):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    return SimpleNamespace(client=TestClient(app), current=current, rag=rag, db=db, student=student, teacher=teacher,
                           subject=subject, lessons=lessons)


def attempt(api, lesson, score, total=10):
    row = QuizAttempt(user_id=api.student.id, lesson_id=lesson.id, score=score, total=total,
                      passed=score * 100 >= 80 * total, missed=json.dumps(list(range(total - score))))
    api.db.add(row)
    api.db.commit()
    return row


def roadmap(api):
    return api.client.get("/learning/roadmap").json()["subjects"][0]


def practice_url(api, lesson, tail=""):
    return f"/subjects/{api.subject.id}/lessons/{lesson.id}/practice{tail}"


# ---------------------------------------------------------------- the roadmap adapts
def test_roadmap_sends_a_struggling_student_back_and_to_easier_practice(api):
    l1, l2, _ = api.lessons
    attempt(api, l1, 8)    # L1 passed, but not mastered
    attempt(api, l2, 5)
    attempt(api, l2, 6)    # two failed tries on L2
    subject = roadmap(api)
    assert [(r["title"], r["level"], r["practice"]) for r in subject["lessons"]] == [
        ("L1", "proficient", None), ("L2", "struggling", "easier"), ("L3", "new", None)]
    item = next(p for p in subject["study_plan"] if p["title"] == "L2")
    assert [s["text"] for s in item["steps"]] == [
        "Review the previous lesson: L1", "Re-read the lesson and your last quiz breakdown",
        "Do the easier practice set", "Retake the quiz (pass at 80%)"]
    assert item["steps"][0]["href"].startswith("lessons.html?subject=") and item["steps"][2]["href"].startswith("practice.html?subject=")
    assert item["level"] == "struggling" and item["minutes"] == sum(s["minutes"] for s in item["steps"])


def test_roadmap_a_near_miss_gets_practice_but_no_extra_review(api):
    attempt(api, api.lessons[0], 7)
    item = roadmap(api)["study_plan"][0]
    assert item["level"] == "developing"
    assert [s["text"] for s in item["steps"]] == [
        "Re-read the lesson and your last quiz breakdown", "Do the easier practice set", "Retake the quiz (pass at 80%)"]


def test_roadmap_fast_tracks_the_lesson_after_a_mastered_one(api):
    attempt(api, api.lessons[0], 10)
    subject = roadmap(api)
    assert subject["lessons"][0]["level"] == "mastered" and subject["lessons"][0]["practice"] == "harder"
    l2, l3 = subject["study_plan"][0], subject["study_plan"][1]
    assert l2["fast_track"] and len(l2["steps"]) == 1 and l2["steps"][0]["text"].startswith("Fast track")
    assert not l3["fast_track"] and l3["steps"][0]["text"] == "Read the lesson"   # only the very next lesson


def test_roadmap_for_a_new_student_is_unchanged(api):
    item = roadmap(api)["study_plan"][0]
    assert [s["text"] for s in item["steps"]] == ["Read the lesson", "Take the quiz (pass at 80%)"]
    assert not item["fast_track"] and item["level"] == "new"


# ---------------------------------------------------------------- practice sets
def test_failed_quiz_gets_an_easier_set_written_once(api):
    l1 = api.lessons[0]
    api.rag.reply = "unused"
    assert api.client.post(practice_url(api, l1, "/generate")).status_code == 400   # no quiz result yet
    attempt(api, l1, 5)
    assert api.client.get(practice_url(api, l1)).json() == {
        "subject": "Algebra", "lesson_title": "L1", "level": "struggling", "kind": "easier", "questions": None}

    api.rag.reply = QUIZ
    made = api.client.post(practice_url(api, l1, "/generate")).json()
    assert made["kind"] == "easier" and len(made["questions"]) == practice_routes.PRACTICE_LENGTH
    assert all("answer" not in q and "explanation" not in q for q in made["questions"])   # answers stay on the server

    api.rag.reply = RuntimeError("must not be called")   # same attempt: the saved set is reused
    assert api.client.post(practice_url(api, l1, "/generate")).json() == made
    assert api.client.get(practice_url(api, l1)).json()["questions"] == made["questions"]


def test_a_new_attempt_gets_a_new_set(api):
    l1 = api.lessons[0]
    attempt(api, l1, 5)
    api.rag.reply = QUIZ
    api.client.post(practice_url(api, l1, "/generate"))
    attempt(api, l1, 6)   # failed again: the old set no longer matches
    assert api.client.get(practice_url(api, l1)).json()["questions"] is None
    api.rag.reply = QUIZ
    assert api.client.post(practice_url(api, l1, "/generate")).status_code == 200
    assert api.db.query(PracticeSet).count() == 1   # replaced, not piled up


def test_the_prompt_asks_for_easier_or_harder_and_names_the_missed_questions(api, monkeypatch):
    seen = []
    async def spy(system, prompt, branch, query):
        seen.append(prompt)
        return QUIZ
    monkeypatch.setattr(practice_routes, "generate_text", spy)
    l1, l2, _ = api.lessons
    api.rag.reply = QUIZ
    assert api.client.post(f"/subjects/{api.subject.id}/lessons/{l1.id}/quiz/generate").status_code == 200   # a stored quiz to miss
    attempt(api, l1, 5)
    attempt(api, l2, 10)
    api.client.post(practice_url(api, l1, "/generate"))
    api.client.post(practice_url(api, l2, "/generate"))
    assert "EASIER" in seen[0] and "Lesson:\n" in seen[0]
    assert "Solve $2x + 6 = 18$." in seen[0] and "Correct answer: " in seen[0]   # the first quiz question was missed
    assert "HARDER" in seen[1] and "missed these questions" not in seen[1]


def test_no_practice_set_after_a_comfortable_pass(api):
    attempt(api, api.lessons[0], 8)   # proficient: passed, nothing extra to do
    assert api.client.get(practice_url(api, api.lessons[0])).json()["kind"] is None
    assert api.client.post(practice_url(api, api.lessons[0], "/generate")).status_code == 400


def test_mastered_student_gets_a_harder_set(api):
    attempt(api, api.lessons[0], 10)
    api.rag.reply = QUIZ
    assert api.client.post(practice_url(api, api.lessons[0], "/generate")).json()["kind"] == "harder"


def test_a_bad_model_reply_is_rejected_and_nothing_is_saved(api):
    attempt(api, api.lessons[0], 5)
    api.rag.reply = "Sorry, I can't do that."
    assert api.client.post(practice_url(api, api.lessons[0], "/generate")).status_code == 502
    assert api.db.query(PracticeSet).count() == 0


def test_practice_is_graded_but_never_recorded(api):
    l1 = api.lessons[0]
    attempt(api, l1, 5)
    api.rag.reply = QUIZ
    questions = api.client.post(practice_url(api, l1, "/generate")).json()["questions"]
    attempts_before = api.db.query(QuizAttempt).count()
    done = api.client.post(practice_url(api, l1, "/submit"), json={"answers": {}}).json()
    assert done["total"] == len(questions) and done["score"] == 0 and done["kind"] == "easier"
    assert all(not r["correct"] and r["correct_answer"] for r in done["results"])
    assert api.db.query(QuizAttempt).count() == attempts_before   # no leaderboard entry, no level change


def test_submitting_without_a_set_is_a_404(api):
    attempt(api, api.lessons[0], 5)
    assert api.client.post(practice_url(api, api.lessons[0], "/submit"), json={"answers": {}}).status_code == 404


def test_deleting_a_lesson_removes_its_practice_sets(api):
    l1 = api.lessons[0]
    attempt(api, l1, 5)
    api.rag.reply = QUIZ
    api.client.post(practice_url(api, l1, "/generate"))
    api.current["user"] = api.teacher
    assert api.client.delete(f"/subjects/{api.subject.id}/lessons/{l1.id}").status_code == 200
    assert api.db.query(PracticeSet).count() == 0


# ---------------------------------------------------------------- the teacher table
def test_teacher_table_counts_each_students_levels(api):
    l1, l2, l3 = api.lessons
    attempt(api, l1, 10)                       # mastered
    attempt(api, l2, 4)                        # struggling
    api.current["user"] = api.teacher
    [row] = api.client.get("/teacher/students").json()
    assert row["levels"] == {"struggling": 1, "developing": 0, "proficient": 0, "mastered": 1}
