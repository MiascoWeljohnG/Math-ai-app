import json

import pytest
from fastapi.testclient import TestClient

import classifier
from models import Material, Subject, User

STATS = "Algebra: 5\nGeometry: 3\nStatistics: 88\nCalculus: 2\nNot mathematics: 2"
UNSURE = "Algebra: 40\nGeometry: 10\nStatistics: 35\nCalculus: 10\nNot mathematics: 5"
NOT_MATH = "Algebra: 2\nGeometry: 2\nStatistics: 2\nCalculus: 2\nNot mathematics: 92"


# ---------------------------------------------------------------- parsing
def test_parse_scores_normalises_and_tolerates_markdown():
    scores = classifier.parse_scores("**Algebra**: 60%\n- Geometry: 20\n* Statistics = 20\nCalculus: 0")
    assert scores["Algebra"] == pytest.approx(0.6)
    assert sum(scores.values()) == pytest.approx(1)


def test_parse_scores_garbage_is_empty():
    assert classifier.parse_scores("I think it's algebra!") == {}
    assert classifier.parse_scores("Algebra: 0\nGeometry: 0") == {}


def test_sample_text_keeps_start_middle_and_end():
    text = "START " + "x" * 20000 + " MIDDLE " + "y" * 20000 + " END"
    sample = classifier.sample_text(text, 1000)
    assert len(sample) < 1100 and sample.startswith("START") and sample.endswith("END")


# ---------------------------------------------------------------- 70% rule
@pytest.mark.parametrize("reply, branch, reason", [
    (STATS, "Statistics", None),              # 88% -> proceed
    (UNSURE, "Algebra", "low_confidence"),    # 40% -> ask
    (NOT_MATH, None, "not_math"),             # not math -> ask
    ("no idea", None, "low_confidence"),      # unreadable reply -> ask
    (RuntimeError("model down"), None, "unavailable"),
])
def test_classify_branch(rag, reply, branch, reason):
    import asyncio
    rag.reply = reply
    result = asyncio.run(classifier.classify_branch("some text"))
    assert result["reason"] == reason
    if reason != "low_confidence":
        assert result["branch"] == branch


def test_threshold_is_exactly_70(rag, monkeypatch):
    import asyncio
    rag.reply = "Algebra: 70\nGeometry: 30\nStatistics: 0\nCalculus: 0\nNot mathematics: 0"
    assert asyncio.run(classifier.classify_branch("x"))["reason"] is None
    rag.reply = "Algebra: 69\nGeometry: 31\nStatistics: 0\nCalculus: 0\nNot mathematics: 0"
    assert asyncio.run(classifier.classify_branch("x"))["reason"] == "low_confidence"


# ---------------------------------------------------------------- admin/teacher upload handler
class FakeUpload:
    def __init__(self, filename, body):
        self.filename, self._body = filename, body

    async def read(self):
        return self._body


def run_upload(db, files, branch=classifier.AUTO, picked=""):
    import asyncio
    return asyncio.run(classifier.ingest_with_detection(
        [FakeUpload(n, b) for n, b in files], branch, picked, "teacher1", db))


def test_confident_file_is_saved_under_detected_branch(rag, db):
    rag.reply = STATS
    out = run_upload(db, [("probability.pdf", b"random variables")])
    assert out["needs_topic"] == []
    assert out["uploaded"][0]["branch"] == "Statistics" and out["uploaded"][0]["auto_detected"]
    assert rag.ingested == [("Statistics", ["probability.pdf"])]
    assert db.query(Material).one().branch == "Statistics"


def test_unsure_file_is_not_saved_and_is_reported(rag, db):
    rag.reply = UNSURE
    out = run_upload(db, [("mixed.docx", b"some text")])
    assert out["uploaded"] == [] and rag.ingested == []
    assert out["needs_topic"][0]["filename"] == "mixed.docx"
    assert out["needs_topic"][0]["reason"] == "low_confidence"
    assert db.query(Material).count() == 0


def test_uploader_pick_is_used_without_asking_the_model(rag, db):
    rag.reply = RuntimeError("must not be called")
    out = run_upload(db, [("mixed.docx", b"some text")], picked=json.dumps({"mixed.docx": "Geometry"}))
    assert out["uploaded"][0]["branch"] == "Geometry" and not out["uploaded"][0]["auto_detected"]
    assert rag.ingested == [("Geometry", ["mixed.docx"])]


def test_explicit_branch_still_works_like_before(rag, db):
    rag.reply = RuntimeError("must not be called")
    out = run_upload(db, [("a.pdf", b"x"), ("b.pdf", b"y")], branch="Calculus")
    assert [u["branch"] for u in out["uploaded"]] == ["Calculus", "Calculus"]
    assert rag.ingested == [("Calculus", ["a.pdf", "b.pdf"])]


def test_mixed_batch_saves_the_sure_ones_and_asks_about_the_rest(rag, db):
    rag.reply = [STATS, UNSURE]
    out = run_upload(db, [("sure.pdf", b"a"), ("unsure.pdf", b"b")])
    assert [u["filename"] for u in out["uploaded"]] == ["sure.pdf"]
    assert [n["filename"] for n in out["needs_topic"]] == ["unsure.pdf"]
    assert "1 file(s) need a topic" in out["message"]


def test_bad_inputs_are_400(rag, db):
    from fastapi import HTTPException
    for kwargs in ({"branch": "Chemistry"}, {"picked": "not json"}, {"picked": json.dumps({"a.pdf": "Nope"})}):
        with pytest.raises(HTTPException) as err:
            run_upload(db, [("a.pdf", b"x")], **kwargs)
        assert err.value.status_code == 400
    with pytest.raises(HTTPException) as err:     # nothing readable (e.g. scanned PDF)
        run_upload(db, [("scan.pdf", b"   ")])
    assert err.value.status_code == 400 and "No readable text" in err.value.detail


# ---------------------------------------------------------------- student endpoints (real routes)
@pytest.fixture
def client(rag, db):
    from fastapi import FastAPI
    import auth
    from database import get_db
    from routes import subjects_routes

    student = User(username="stu", password_hash="x", role="user")
    db.add(student)
    db.add(Subject(name="Trigonometry", description="Sine, cosine and triangles", owner_user_id=None))
    db.commit()
    mine = Subject(name="Probability", description="Chance and random variables", owner_user_id=student.id)
    db.add(mine)
    db.commit()

    app = FastAPI()
    app.include_router(subjects_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: student
    test_client = TestClient(app)
    test_client.personal_id = mine.id
    return test_client


def test_suggest_fills_title_and_description(client, rag):
    rag.reply = "TITLE: **Random Variables**\nDESCRIPTION: Learn discrete and continuous random variables."
    res = client.post("/subjects/suggest", files={"file": ("m.pdf", b"random variables text")})
    assert res.status_code == 200
    assert res.json() == {"name": "Random Variables", "description": "Learn discrete and continuous random variables."}


def test_suggest_truncates_to_the_subject_limits(client, rag):
    rag.reply = f"TITLE: {'T' * 200}\nDESCRIPTION: {'D' * 900}"
    body = client.post("/subjects/suggest", files={"file": ("m.docx", b"text")}).json()
    assert len(body["name"]) == 80 and len(body["description"]) == 500


def test_suggest_rejects_unreadable_and_unparseable(client, rag):
    assert client.post("/subjects/suggest", files={"file": ("m.pdf", b"  ")}).status_code == 400
    rag.reply = "sorry, can't"
    assert client.post("/subjects/suggest", files={"file": ("m.pdf", b"text")}).status_code == 502


def test_related_file_generates_a_lesson(client, rag):
    rag.reply = [
        "DETECTED_TOPIC: Random variables\nRELEVANCE: 92",          # relevance check
        "TITLE: Random Variables Basics\nDESCRIPTION: Intro.",       # title (no topic typed)
        "## Intro\nA random variable maps outcomes to numbers.",     # lesson
    ]
    res = client.post(f"/subjects/{client.personal_id}/lessons/generate-from-file", files={"file": ("m.pdf", b"text")})
    body = res.json()
    assert res.status_code == 200 and body["status"] == "ok"
    assert body["title"] == "Random Variables Basics" and "random variable" in body["content"]
    assert client.get(f"/subjects/{client.personal_id}/lessons").json()[0]["title"] == "Random Variables Basics"


def test_unrelated_file_warns_and_creates_nothing(client, rag):
    rag.reply = "DETECTED_TOPIC: Photosynthesis in plants\nRELEVANCE: 8"
    res = client.post(f"/subjects/{client.personal_id}/lessons/generate-from-file", files={"file": ("bio.pdf", b"text")})
    assert res.status_code == 200
    assert res.json()["status"] == "mismatch" and res.json()["detected_topic"] == "Photosynthesis in plants"
    assert client.get(f"/subjects/{client.personal_id}/lessons").json() == []


def test_force_skips_the_check_and_typed_topic_is_the_title(client, rag):
    rag.reply = "## Body\nLesson text."          # only the lesson call happens
    res = client.post(
        f"/subjects/{client.personal_id}/lessons/generate-from-file",
        files={"file": ("bio.pdf", b"text")}, data={"topic": "My topic", "force": "true"},
    )
    assert res.status_code == 200 and res.json()["status"] == "ok" and res.json()["title"] == "My topic"


def test_cannot_generate_into_someone_elses_or_a_shared_subject(client, rag, db):
    shared = db.query(Subject).filter(Subject.owner_user_id.is_(None)).first()
    res = client.post(f"/subjects/{shared.id}/lessons/generate-from-file", files={"file": ("m.pdf", b"text")})
    assert res.status_code == 403      # students can't write to shared subjects


# ---------------------------------------------------------------- lessons from a whole file
def test_relevant_text_finds_the_pages_about_the_topic():
    filler = "unrelated words about weather and cooking. " * 200
    text = filler + " the quadratic formula solves quadratic equations. " * 30 + filler
    picked = classifier.relevant_text(text, "Quadratic Formula", limit=3000)
    assert "quadratic formula" in picked and len(picked) <= 3200
    assert classifier.relevant_text("short doc", "anything") == "short doc"


def test_outline_from_file_returns_clean_titles(client, rag):
    rag.reply = "1. Square Roots\n- Factoring\n**Completing the Square**\n\nThe Quadratic Formula\nExtra Title"
    res = client.post(
        f"/subjects/{client.personal_id}/lessons/outline-from-file",
        files={"file": ("m.pdf", b"text")}, data={"count": "4"},
    )
    assert res.status_code == 200
    assert res.json()["titles"] == ["Square Roots", "Factoring", "Completing the Square", "The Quadratic Formula"]


def test_outline_from_file_rejects_other_peoples_subjects(client, rag, db):
    shared = db.query(Subject).filter(Subject.owner_user_id.is_(None)).first()
    res = client.post(f"/subjects/{shared.id}/lessons/outline-from-file", files={"file": ("m.pdf", b"text")})
    assert res.status_code == 403
