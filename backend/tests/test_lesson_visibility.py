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
    from routes import games_routes
    app.include_router(games_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: who["user"]
    app.dependency_overrides[auth.require_staff] = lambda: teacher
    app.dependency_overrides[games_routes.require_staff] = lambda: who["user"] if who["user"].role in ("teacher", "school_admin") else (_ for _ in ()).throw(__import__("fastapi").HTTPException(status_code=403, detail="Staff only"))
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


def test_teacher_can_assign_preferred_game_and_students_see_it(world, rag):
    lesson = add(world, "published")
    response = world.put(
        f"/subjects/{world.shared.id}/lessons/{lesson.id}/preferred-game",
        json={"game_id": "matching"},
    )
    assert response.status_code == 403  # Test fixture runs as the student until explicitly switched.
    world.as_teacher()
    response = world.put(
        f"/subjects/{world.shared.id}/lessons/{lesson.id}/preferred-game",
        json={"game_id": "matching"},
    )
    assert response.status_code == 200
    assert response.json()["preferred_game"] == "matching"
    world.as_student()
    visible = world.get(f"/subjects/{world.shared.id}/lessons/{lesson.id}")
    assert visible.status_code == 200
    assert visible.json()["preferred_game"] == "matching"


def test_student_cannot_assign_preferred_game(world):
    lesson = add(world, "published")
    response = world.put(
        f"/subjects/{world.shared.id}/lessons/{lesson.id}/preferred-game",
        json={"game_id": "matching"},
    )
    assert response.status_code == 403


def test_invalid_preferred_game_is_rejected(world):
    world.as_teacher()
    lesson = add(world, "published")
    response = world.put(
        f"/subjects/{world.shared.id}/lessons/{lesson.id}/preferred-game",
        json={"game_id": "not-a-game"},
    )
    assert response.status_code == 400


def test_teacher_existing_lesson_has_game_selector_and_save_action():
    from pathlib import Path
    source = Path(__file__).resolve().parents[2].joinpath("frontend/js/lessons.js").read_text()
    assert 'function buildLessonGamePanel(subjectId, lesson)' in source
    assert 'Choose a game for this lesson' in source
    assert 'Save game' in source
    assert 'preferred-game' in source


def test_teacher_can_clear_a_lesson_game(world):
    world.as_teacher()
    lesson = add(world, "published")
    url = f"/subjects/{world.shared.id}/lessons/{lesson.id}/preferred-game"
    assert world.put(url, json={"game_id": "hangman"}).json()["preferred_game"] == "hangman"
    cleared = world.put(url, json={"game_id": ""})
    assert cleared.status_code == 200
    assert cleared.json()["preferred_game"] is None


def test_manage_lessons_page_has_game_picker_wired():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "frontend"
    html = (root / "manage-lessons.html").read_text()
    script = (root / "js/teacher.js").read_text()
    assert 'id="lessonGameSelect"' in html
    assert "saveLessonGame" in script and "preferred-game" in script


def test_games_page_deep_link_can_see_subjects():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "frontend/js/games.js").read_text()
    assert "let subjects = [];" in source   # was a const inside the try block: the deep link threw a ReferenceError


# ---------------------------------------------------------------- generated game content
PACK = {"terms": [{"word": "SQUARE", "clue": "A number times itself"}] * 4}


@pytest.fixture
def pack_model(monkeypatch):
    """Stands in for the AI: counts how often it is asked and returns PACK as JSON."""
    import json
    from routes import games_routes
    calls = []

    async def fake(system, prompt, branch, query, school_id=None):
        calls.append(prompt)
        return json.dumps({"terms": [{"word": "SQUARE", "clue": "A number times itself"},
                                     {"word": "CUBES", "clue": "Three equal factors"},
                                     {"word": "ROOTS", "clue": "Undo a power"},
                                     {"word": "POWER", "clue": "The little raised number"}]})

    monkeypatch.setattr(games_routes, "generate_text", fake)
    games_routes._CACHE.clear()
    return calls


def test_teacher_generates_game_content_and_students_get_that_same_version(world, pack_model):
    lesson = add(world, "published")
    url = f"/subjects/{world.shared.id}/lessons/{lesson.id}"
    world.as_teacher()
    assert world.get(url).json()["game_status"] == "none"
    made = world.post(url + "/games/generate")
    assert made.status_code == 200 and made.json()["game_status"] == "ready"
    assert [t["word"] for t in made.json()["pack"]["terms"]] == ["SQUARE", "CUBES", "ROOTS", "POWER"]
    assert world.get(url).json()["game_status"] == "ready"

    from routes import games_routes
    games_routes._CACHE.clear()          # even after a restart (empty cache) ...
    calls_before = len(pack_model)
    world.as_student()
    assert world.post(url + "/games").json() == made.json()["pack"]
    assert len(pack_model) == calls_before   # ... the student is served from the lesson, not by asking the AI again


def test_changing_the_lesson_text_makes_the_game_content_stale(world, pack_model):
    lesson = add(world, "published")
    url = f"/subjects/{world.shared.id}/lessons/{lesson.id}"
    world.as_teacher()
    world.post(url + "/games/generate")
    lesson.content = "A different lesson now."
    world.db.commit()
    assert world.get(url).json()["game_status"] == "stale"
    asked = len(pack_model)
    world.as_student()
    world.post(url + "/games")              # a stale pack is not served: the page gets one for the new text
    assert len(pack_model) > asked           # the model was asked again (it retries when a pack is thin)


def test_only_staff_generate_game_content_and_an_empty_lesson_is_refused(world, pack_model):
    lesson = add(world, "published")
    url = f"/subjects/{world.shared.id}/lessons/{lesson.id}/games/generate"
    world.as_student()
    assert world.post(url).status_code == 403
    world.as_teacher()
    lesson.content = "  "
    world.db.commit()
    assert world.post(url).status_code == 400
    assert pack_model == []


def test_manage_lessons_has_the_generate_game_button():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "frontend"
    assert 'id="lessonGameGenerateBtn"' in (root / "manage-lessons.html").read_text()
    script = (root / "js/teacher.js").read_text()
    assert "games/generate" in script and "renderGamePack" in script
