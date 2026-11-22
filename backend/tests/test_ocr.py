"""Reading scans (ocr.py): the vision models are tried in turn. No network: the model calls are replaced."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw  # noqa: E402

import config  # noqa: E402
import ocr  # noqa: E402


def sample_image() -> Image.Image:
    image = Image.new("RGB", (800, 400), "white")
    ImageDraw.Draw(image).text((40, 40), "25% of 80 = 20", fill="black")
    return image


def sample_png() -> bytes:
    out = io.BytesIO()
    sample_image().save(out, "PNG")
    return out.getvalue()


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    """Groq and Gemini look set up; nothing is paused from an earlier test; no real call is ever made."""
    monkeypatch.setattr(config, "GROQ_API_KEY", "x")
    monkeypatch.setattr(config, "GROQ_VISION_MODEL", "vision-model")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "y")
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", "")
    monkeypatch.setattr(ocr, "PROVIDERS", ["groq", "gemini", "ollama"])
    monkeypatch.setattr(ocr, "_paused_until", {})
    monkeypatch.setattr(ocr, "_call", lambda name, b64: pytest.fail(f"unexpected call to {name}"))


def test_the_first_provider_that_answers_is_used(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "_call", lambda name, b64: calls.append(name) or "25% of 80 = 20")
    assert ocr.ocr_image(sample_image()) == "25% of 80 = 20"
    assert calls == ["groq"]


def test_the_next_provider_is_tried_when_one_cannot_answer(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "_call", lambda name, b64: calls.append(name) or (None if name == "groq" else "from gemini"))
    assert ocr.ocr_image(sample_image()) == "from gemini"
    assert calls == ["groq", "gemini"]


def test_a_paused_provider_is_skipped(monkeypatch):
    import time
    ocr._paused_until["groq"] = time.time() + 600
    calls = []
    monkeypatch.setattr(ocr, "_call", lambda name, b64: calls.append(name) or "text")
    ocr.ocr_image(sample_image())
    assert calls == ["gemini"]


def test_the_answer_is_cleaned(monkeypatch):
    monkeypatch.setattr(ocr, "_call", lambda name, b64: "<think>hm</think>```text\nLine one\nLine two\n```")
    assert ocr.ocr_image(sample_image()) == "Line one\nLine two"
    monkeypatch.setattr(ocr, "_call", lambda name, b64: "NONE")
    assert ocr.ocr_image(sample_image()) == ""


def test_a_blank_page_is_not_sent_anywhere():
    assert ocr.ocr_image(Image.new("RGB", (400, 300), "white")) == ""   # an unexpected call would fail the test


def test_when_nothing_can_read_the_page_the_reason_is_given(monkeypatch):
    monkeypatch.setattr(ocr, "_call", lambda name, b64: None)
    with pytest.raises(ocr.OcrUnavailable, match="busy"):
        ocr.ocr_image(sample_image())


def test_with_no_vision_model_set_up_the_page_cannot_be_read(monkeypatch):
    monkeypatch.setattr(config, "GROQ_VISION_MODEL", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert not ocr.available()
    with pytest.raises(ocr.OcrUnavailable, match="set up"):
        ocr.ocr_image(sample_image())


def test_a_photo_becomes_a_one_page_pdf_whose_picture_can_be_read(monkeypatch):
    pdf = ocr.image_to_pdf(sample_png())
    assert pdf.startswith(b"%PDF")
    import pdfplumber
    monkeypatch.setattr(ocr, "_call", lambda name, b64: "25% of 80 = 20")
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        assert len(document.pages) == 1
        assert not (document.pages[0].extract_text() or "").strip()   # a scan: no text layer
        assert "25%" in ocr.ocr_pdf_page(document.pages[0])


def test_a_photo_file_is_read_through_the_same_chain(monkeypatch):
    monkeypatch.setattr(ocr, "_call", lambda name, b64: "photo text")
    assert ocr.ocr_image_bytes(sample_png()) == "photo text"
