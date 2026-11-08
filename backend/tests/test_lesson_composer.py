"""The teacher's "create lessons" form: plan 1-6 titles, then write each lesson from its description."""
import pytest
from fastapi.testclient import TestClient

from models import Lesson, Subject, User


@pytest.fixture
def api(rag, db):
    from fastapi import FastAPI
    import auth
    from database import get_db
    from routes import subjects_routes

    teacher = User(username="teach", password_hash="x", role="teacher")
    db.add(teacher)
    subject = Subject(name="Algebra", description="Equations", owner_user_id=None)
    db.add(subject)
    db.commit()

    app = FastAPI()
    app.include_router(subjects_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: teacher
    app.dependency_overrides[auth.require_staff] = lambda: teacher
    client = TestClient(app)
    client.staff_api = lambda: (app.dependency_overrides.__setitem__(auth.require_staff, lambda: teacher) or TestClient(app))
    client.sid = subject.id
    client.url = f"/subjects/{subject.id}/lessons"
    return client


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6])
def test_plan_returns_exactly_the_requested_number(api, rag, count):
    rag.reply = "\n".join(f"{i}. Topic {i}" for i in range(1, 9))    # model over-delivers
    res = api.post(f"{api.url}/plan", data={"count": count})
    assert res.status_code == 200
    assert res.json()["titles"] == [f"Topic {i}" for i in range(1, count + 1)]


@pytest.mark.parametrize("count", [0, 7])
def test_plan_rejects_counts_outside_1_to_6(api, rag, count):
    assert api.post(f"{api.url}/plan", data={"count": count}).status_code == 422


def test_plan_skips_titles_that_already_exist_or_were_typed(api, rag, db):
    db.add(Lesson(subject_id=api.sid, title="Variables", content="x", created_by="t"))
    db.commit()
    rag.reply = "variables\nMy typed one\nExponents\nFactoring"
    res = api.post(f"{api.url}/plan", data={"count": 2, "existing": "My typed one"})
    assert res.json()["titles"] == ["Exponents", "Factoring"]


def test_plan_can_use_an_uploaded_pdf(api, rag):
    rag.reply = "Slope\nIntercepts"
    res = api.post(f"{api.url}/plan", data={"count": 2, "description": "lines"},
                   files={"file": ("w1.pdf", b"slope and intercept text")})
    assert res.status_code == 200 and res.json()["titles"] == ["Slope", "Intercepts"]


def test_plan_with_an_unreadable_pdf_is_a_400(api, rag):
    res = api.post(f"{api.url}/plan", data={"count": 1}, files={"file": ("scan.pdf", b"   ")})
    assert res.status_code == 400 and "No readable text" in res.json()["detail"]


def test_selected_uploaded_pdf_prefills_editable_lesson_fields(api, rag):
    rag.reply = [
        "TITLE: Linear Equations\nDESCRIPTION: Solve equations using inverse operations.",
        "## Solve\nUndo operations to isolate the variable.",
    ]
    res = api.post(f"/subjects/{api.sid}/lessons/suggest-from-file", files={"file": ("linear.pdf", b"solve x + 3 = 7")})
    assert res.status_code == 200
    assert res.json() == {
        "title": "Linear Equations",
        "description": "Solve equations using inverse operations.",
        "content": "## Solve\nUndo operations to isolate the variable.",
    }


def test_selected_uploaded_docx_prefills_editable_lesson_fields(api, rag):
    rag.reply = [
        "TITLE: Fractions\nDESCRIPTION: Compare fractions with common denominators.",
        "## Compare\nUse equivalent fractions.",
    ]
    res = api.post(f"/subjects/{api.sid}/lessons/suggest-from-file", files={"file": ("fractions.docx", b"compare 1/2 and 3/4")})
    assert res.status_code == 200
    assert res.json()["title"] == "Fractions"
    assert "common denominators" in res.json()["description"]
    assert "equivalent fractions" in res.json()["content"]


def test_compose_saves_generated_content_as_a_hidden_draft(api, rag):
    rag.reply = "## Idea\nAn equation balances two sides."
    res = api.post(f"{api.url}/compose", data={"title": "Balancing", "description": "use a scale analogy"})
    body = res.json()
    assert res.status_code == 200
    assert body["title"] == "Balancing" and body["description"] == "use a scale analogy"
    assert body["status"] == "draft"
    assert "balances" in body["content"]
    stored = api.get(f"{api.url}/{body['id']}").json()
    assert stored["description"] == "use a scale analogy" and stored["content"] == body["content"]
    assert api.get(api.url).json() == []  # students must not see drafts


def test_draft_review_edit_and_approve_workflow(api, rag, db):
    rag.reply = "Fresh regenerated lesson"
    lesson = api.post(f"{api.url}/compose", data={"title": "Review me"}).json()
    # Staff gets a dedicated draft collection; the student route stays published-only.
    staff_api = api.staff_api()
    drafts = staff_api.get(f"{api.url}/drafts")
    assert drafts.status_code == 200
    assert [item["id"] for item in drafts.json()] == [lesson["id"]]
    assert api.get(api.url).json() == []

    edited = staff_api.put(f"{api.url}/{lesson['id']}/draft", json={
        "title": "Edited", "content": "Teacher-edited content", "description": "Reviewed"
    })
    assert edited.status_code == 200 and edited.json()["status"] == "draft"
    assert edited.json()["content"] == "Teacher-edited content"

    retried = staff_api.post(f"{api.url}/{lesson['id']}/retry")
    assert retried.status_code == 200 and retried.json()["status"] == "draft"
    assert retried.json()["content"] == "Fresh regenerated lesson"

    approved = staff_api.post(f"{api.url}/{lesson['id']}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "published"
    assert api.get(api.url).json()[0]["title"] == "Edited"
    assert staff_api.get(f"{api.url}/drafts").json() == []


def test_compose_without_save_returns_content_and_stores_nothing(api, rag):
    rag.reply = "New text"
    res = api.post(f"{api.url}/compose", data={"title": "T", "save": "false"})
    assert res.json() == {"title": "T", "description": "", "content": "New text", "source_name": ""}
    assert api.get(api.url).json() == []


def test_compose_from_a_pdf_and_keeps_lessons_in_order(api, rag):
    rag.reply = ["First body", "Second body"]
    series = "One\nTwo"
    for title in ("One", "Two"):
        res = api.post(f"{api.url}/compose", data={"title": title, "series": series},
                       files={"file": ("m.pdf", b"some text")})
        assert res.status_code == 200
    assert [l["title"] for l in api.get(api.url).json()] == []
    assert [l["title"] for l in api.staff_api().get(f"{api.url}/drafts").json()] == ["One", "Two"]


def test_compose_prompt_mentions_description_series_and_source(api):
    from routes import subjects_routes as r
    subject = Subject(name="Algebra")
    prompt = r._compose_prompt(subject, "Two", "focus on fractions", ["One", "Two", "Three"], "document words")
    assert "focus on fractions" in prompt and "one of 3" in prompt and "document words" in prompt
    plain = r._compose_prompt(subject, "Solo", "", ["Solo"], None)
    assert "series" not in plain and "Source document" not in plain


def test_compose_requires_a_title_and_reports_model_failures(api, rag):
    assert api.post(f"{api.url}/compose", data={"title": "   "}).status_code == 400
    rag.reply = RuntimeError("model down")
    assert api.post(f"{api.url}/compose", data={"title": "T"}).status_code == 502
    rag.reply = ""
    assert api.post(f"{api.url}/compose", data={"title": "T"}).status_code == 502
    assert api.get(api.url).json() == []


def test_overlong_description_is_rejected(api, rag):
    rag.reply = "x"
    assert api.post(f"{api.url}/compose", data={"title": "T", "description": "d" * 5001}).status_code == 400


def test_description_can_be_edited_through_the_normal_update(api, rag):
    lesson = api.post(f"{api.url}", json={"title": "A", "content": "c", "description": "d1"}).json()
    assert lesson["description"] == "d1"
    out = api.put(f"{api.url}/{lesson['id']}", json={"title": "A", "content": "c2", "description": "d2"}).json()
    assert out["description"] == "d2" and out["content"] == "c2"
    # an old client that doesn't send a description leaves it alone
    out = api.put(f"{api.url}/{lesson['id']}", json={"title": "A", "content": "c3"}).json()
    assert out["description"] == "d2"


def test_browser_style_crlf_line_breaks_in_titles_are_understood(api, rag, db):
    """Browsers send \r\n inside form values; typed titles must still be split and de-duplicated."""
    rag.reply = "Typed one\nNew one"
    res = api.post(f"{api.url}/plan", data={"count": 1, "existing": "Typed one\r\nTyped two"})
    assert res.json()["titles"] == ["New one"]


# --- page ranges: write a lesson from, say, pages 20-30 of a long module -----------------------------------

@pytest.fixture
def module_pages(rag, monkeypatch):
    """A 40-page 'module' where page N says 'content of page N', and a way to see what the model was shown."""
    seen = []

    def fake_extract(filename, contents, page_range=None):
        if filename.endswith(".docx"):
            return [(0, "no pages here", [])]
        low, high = page_range or (1, 40)
        return [(n, f"content of page {n}", []) for n in range(low, min(high, 40) + 1)]

    async def fake_generate(system, prompt, branch, query):
        seen.append(prompt)
        return "## Lesson\nbody"

    from routes import subjects_routes   # it imported generate_text by name, so patch it there
    monkeypatch.setattr(rag, "extract_text_from_bytes", fake_extract)
    monkeypatch.setattr(subjects_routes, "generate_text", fake_generate)
    return seen


def _compose(api, **extra):
    data = {"title": "Factoring", "save": "false", **extra}
    return api.post(f"{api.url}/compose", data=data, files={"file": ("module.pdf", b"x")})


def test_compose_uses_only_the_requested_pages(api, module_pages):
    res = _compose(api, page_start="20", page_end="30")
    assert res.status_code == 200
    prompt = module_pages[-1]
    assert "content of page 20" in prompt and "content of page 30" in prompt
    assert "content of page 19" not in prompt and "content of page 31" not in prompt
    assert "pages 20-30" in prompt


def test_compose_single_page_when_only_start_given(api, module_pages):
    assert _compose(api, page_start="7").status_code == 200
    prompt = module_pages[-1]
    assert "content of page 7" in prompt and "content of page 8" not in prompt
    assert "page 7 of a longer module" in prompt


def test_compose_without_a_range_still_reads_the_whole_file(api, module_pages):
    assert _compose(api).status_code == 200
    assert "content of page 1" in module_pages[-1] and "content of page 40" in module_pages[-1]


def test_page_range_outside_the_document_is_a_clear_400(api, module_pages):
    res = _compose(api, page_start="300", page_end="310")
    assert res.status_code == 400 and "last page with text is 40" in res.json()["detail"]


@pytest.mark.parametrize("start,end", [("0", "5"), ("30", "20"), ("abc", "5")])
def test_bad_page_numbers_are_rejected(api, module_pages, start, end):
    assert _compose(api, page_start=start, page_end=end).status_code == 400


def test_page_range_on_a_docx_explains_why_it_cant_work(api, module_pages):
    res = api.post(f"{api.url}/compose", data={"title": "T", "save": "false", "page_start": "1", "page_end": "2"},
                   files={"file": ("module.docx", b"x")})
    assert res.status_code == 400 and "no page numbers" in res.json()["detail"]


def test_page_range_without_a_file_is_rejected(api, module_pages):
    res = api.post(f"{api.url}/compose", data={"title": "T", "save": "false", "page_start": "1", "page_end": "2"})
    assert res.status_code == 400 and "needs a source file" in res.json()["detail"]


def test_plan_titles_come_from_the_requested_pages(api, module_pages, monkeypatch):
    from routes import subjects_routes

    async def fake_generate(system, prompt, branch, query):
        module_pages.append(prompt)
        return "Topic A\nTopic B"
    monkeypatch.setattr(subjects_routes, "generate_text", fake_generate)
    res = api.post(f"{api.url}/plan", data={"count": 2, "page_start": "20", "page_end": "22"},
                   files={"file": ("module.pdf", b"x")})
    assert res.status_code == 200
    assert "content of page 21" in module_pages[-1] and "content of page 23" not in module_pages[-1]
