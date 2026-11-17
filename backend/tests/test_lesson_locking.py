"""Lesson locking: a student opens a shared subject's lessons in order. Passing the quiz or marking a lesson complete
unlocks the next one. Teachers and a student's own personal subject are never locked."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models import Lesson, LessonQuiz, Subject, User


@pytest.fixture
def world(rag, db):
    import auth
    from database import get_db
    from routes import subjects_routes

    teacher = User(username="teach", password_hash="x", role="teacher")
    student = User(username="stud", password_hash="x", role="user")
    db.add_all([teacher, student])
    db.commit()
    shared = Subject(name="Algebra", description="", owner_user_id=None)
    personal = Subject(name="My own topic", description="", owner_user_id=student.id)
    db.add_all([shared, personal])
    db.commit()

    who = {"user": student}
    app = FastAPI()
    app.include_router(subjects_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: who["user"]
    app.dependency_overrides[auth.require_staff] = lambda: teacher
    client = TestClient(app)
    client.as_teacher = lambda: who.update(user=teacher)
    client.shared, client.personal, client.db = shared, personal, db
    return client


def make_lessons(world, subject=None, count=3):
    subject = subject or world.shared
    lessons = []
    for i in range(count):
        lesson = Lesson(subject_id=subject.id, title=f"Lesson {i + 1}", content="c", created_by="teach",
                        status="published", order_index=i)
        world.db.add(lesson)
        world.db.commit()
        lessons.append(lesson)
    return lessons


def states(world, subject=None):
    rows = world.get(f"/subjects/{(subject or world.shared).id}/lessons").json()
    return [(r["completed"], r["locked"]) for r in rows]


def test_only_the_first_lesson_is_open_at_the_start(world):
    make_lessons(world)
    assert states(world) == [(False, False), (False, True), (False, True)]


def test_a_locked_lesson_and_its_quiz_cannot_be_opened_by_guessing_the_id(world):
    one, two, _ = make_lessons(world)
    base = f"/subjects/{world.shared.id}/lessons"
    assert world.get(f"{base}/{one.id}").status_code == 200
    assert world.get(f"{base}/{two.id}").status_code == 403
    assert world.get(f"{base}/{two.id}/quiz").status_code == 403
    assert world.post(f"{base}/{two.id}/quiz/generate").status_code == 403
    assert world.post(f"{base}/{two.id}/quiz/submit", json={"answers": {}}).status_code == 403


def test_marking_a_lesson_complete_unlocks_the_next_one(world):
    one, two, _ = make_lessons(world)
    base = f"/subjects/{world.shared.id}/lessons"
    assert world.put(f"{base}/{one.id}/completion", json={"completed": True}).status_code == 200
    assert states(world) == [(True, False), (False, False), (False, True)]
    assert world.get(f"{base}/{two.id}").status_code == 200


def test_undoing_a_lesson_locks_everything_after_it_again(world):
    one, two, _ = make_lessons(world)
    base = f"/subjects/{world.shared.id}/lessons"
    world.put(f"{base}/{one.id}/completion", json={"completed": True})
    world.put(f"{base}/{two.id}/completion", json={"completed": True})
    assert states(world) == [(True, False), (True, False), (False, False)]
    world.put(f"{base}/{one.id}/completion", json={"completed": False})
    assert states(world) == [(False, False), (True, True), (False, True)]


def test_passing_the_quiz_completes_the_lesson_and_unlocks_the_next(world):
    one, two, _ = make_lessons(world)
    questions = [{"type": "mcq", "question": "1+1?", "choices": ["1", "2", "3", "4"], "answer": 1, "explanation": "two"}]
    world.db.add(LessonQuiz(lesson_id=one.id, questions=json.dumps(questions), difficulty=3))
    world.db.commit()
    base = f"/subjects/{world.shared.id}/lessons"

    failed = world.post(f"{base}/{one.id}/quiz/submit", json={"answers": {"0": 0}}).json()
    assert failed["passed"] is False
    assert states(world) == [(False, False), (False, True), (False, True)]   # a fail does not unlock anything

    passed = world.post(f"{base}/{one.id}/quiz/submit", json={"answers": {"0": 1}}).json()
    assert passed["passed"] is True
    assert states(world) == [(True, False), (False, False), (False, True)]


def test_teachers_are_never_locked(world):
    one, two, three = make_lessons(world)
    world.as_teacher()
    assert states(world) == [(False, False)] * 3
    assert world.get(f"/subjects/{world.shared.id}/lessons/{three.id}").status_code == 200


def test_a_students_own_subject_is_never_locked(world):
    _, _, three = make_lessons(world, subject=world.personal)
    assert states(world, world.personal) == [(False, False)] * 3
    assert world.get(f"/subjects/{world.personal.id}/lessons/{three.id}").status_code == 200
