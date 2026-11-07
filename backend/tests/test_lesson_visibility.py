"""Who can see which lessons: teachers' AI lessons wait as drafts, students' own lessons don't, and drafts never leak."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models import Lesson, Subject, User


@pytest.fixture
def world(rag, db):
    import auth
    from database import get_db
    from routes import learning_routes, subjects_routes

    teacher = User(username="teach", password_hash="x", role="teacher")
    student = User(username="stud", password_hash="x", role="student")
    db.add_all([teacher, student])
    db.commit()
    shared = Subject(name="Algebra", description="", owner_user_id=None)
    personal = Subject(name="My own topic", description="", owner_user_id=student.id)
    db.add_all([shared, personal])
    db.commit()

    who = {"user": student}
    app = FastAPI()
    app.include_router(subjects_routes.router)
    app.include_router(learning_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: who["user"]
    app.dependency_overrides[auth.require_staff] = lambda: teacher
    client = TestClient(app)
    client.as_teacher = lambda: who.update(user=teacher)
    client.as_student = lambda: who.update(user=student)
    client.shared, client.personal, client.db = shared, personal, db
    return client


def add(world, status, title="L", subject=None):
    lesson = Lesson(subject_id=(subject or world.shared).id, title=title, content="c", created_by="teach", status=status)
    world.db.add(lesson)
    world.db.commit()
    return lesson


def test_a_student_cannot_open_a_draft_by_guessing_its_id(world):
    draft = add(world, "draft")
    assert world.get(f"/subjects/{world.shared.id}/lessons/{draft.id}").status_code == 404
    world.as_teacher()
    assert world.get(f"/subjects/{world.shared.id}/lessons/{draft.id}").status_code == 200   # the teacher can review it


def test_the_roadmap_counts_only_the_lessons_a_student_can_open(world):
    add(world, "published", "One"); add(world, "published", "Two")
    for i in range(5):
        add(world, "draft", f"Draft {i}")
    entry = next(s for s in world.get("/learning/roadmap").json()["subjects"] if s["branch"] == "Algebra")
    assert entry["total"] == 2 and [lesson["title"] for lesson in entry["lessons"]] == ["One", "Two"]
    assert len(world.get(f"/subjects/{world.shared.id}/lessons").json()) == 2   # same number as the Lessons page


def test_a_students_own_generated_lesson_is_published_straight_away(world, rag):
    rag.reply = "## Idea\nSomething useful."
    made = world.post(f"/subjects/{world.personal.id}/lessons/generate", json={"topic": "Fractions"})
    assert made.status_code == 200 and made.json()["status"] == "published"
    assert [lesson["title"] for lesson in world.get(f"/subjects/{world.personal.id}/lessons").json()] == ["Fractions"]


def test_a_teachers_generated_lesson_waits_as_a_draft(world, rag):
    world.as_teacher()
    rag.reply = "## Idea\nSomething useful."
    made = world.post(f"/subjects/{world.shared.id}/lessons/generate", json={"topic": "Fractions"})
    assert made.json()["status"] == "draft"
    assert world.get(f"/subjects/{world.shared.id}/lessons").json() == []
    assert [lesson["title"] for lesson in world.get(f"/subjects/{world.shared.id}/lessons/drafts").json()] == ["Fractions"]
