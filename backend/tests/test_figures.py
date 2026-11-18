"""Diagrams inside documents (figures.py): labels read with OCR, plus an optional vision-model description."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("rapidocr_onnxruntime")
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import config  # noqa: E402
import figures  # noqa: E402


def diagram_png(label="Hypotenuse 10 cm") -> bytes:
    image = Image.new("RGB", (600, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(60, 300), (520, 300), (60, 60)], outline="black", width=4)
    try:
        font = ImageFont.load_default(size=34)
    except TypeError:
        font = ImageFont.load_default()
    draw.text((150, 150), label, fill="black", font=font)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


@pytest.fixture(autouse=True)
def no_vision(monkeypatch):
    monkeypatch.setattr(config, "GROQ_VISION_MODEL", "")


def test_labels_inside_a_figure_are_read():
    note = figures.blob_note(diagram_png(), figures.Budget())
    assert note.startswith("[Figure: Text in the figure:") and "10 cm" in note


def test_a_vision_description_is_added_when_a_model_is_set(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "x")
    monkeypatch.setattr(config, "GROQ_VISION_MODEL", "some-vision-model")
    monkeypatch.setattr(figures, "_describe", lambda image: "A right triangle with the hypotenuse labelled 10 cm.")
    note = figures.blob_note(diagram_png(), figures.Budget())
    assert note.startswith("[Figure: A right triangle with the hypotenuse labelled 10 cm. Text in the figure:")


def test_decoration_the_model_calls_none_adds_nothing(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "x")
    monkeypatch.setattr(config, "GROQ_VISION_MODEL", "some-vision-model")
    monkeypatch.setattr(config, "FIGURE_OCR", False)
    monkeypatch.setattr(figures, "_describe", lambda image: "")
    assert figures.blob_note(diagram_png(), figures.Budget()) == ""


def test_icons_repeated_logos_and_the_per_file_limit(monkeypatch):
    tiny = io.BytesIO()
    Image.new("RGB", (40, 40), "black").save(tiny, "PNG")
    assert figures.blob_note(tiny.getvalue(), figures.Budget()) == ""            # too small to be a figure
    budget = figures.Budget()
    assert figures.blob_note(diagram_png(), budget) != ""
    assert figures.blob_note(diagram_png(), budget) == ""                        # the same picture again (a logo)
    monkeypatch.setattr(config, "FIGURE_MAX_OCR", 1)
    limited = figures.Budget()
    figures.blob_note(diagram_png("One"), limited)
    assert figures.blob_note(diagram_png("Two two two"), limited) == ""          # the budget for this file is spent


def test_a_word_file_with_a_diagram_gets_its_labels_in_the_text():
    from docx import Document
    from docx.shared import Inches
    document = Document()
    document.add_paragraph("The Pythagorean theorem relates the sides of a right triangle.")
    document.add_picture(io.BytesIO(diagram_png()), width=Inches(4))
    notes = figures.docx_notes(document, figures.Budget())
    assert len(notes) == 1 and "10 cm" in notes[0]


def test_a_pdf_page_with_a_diagram_gets_its_labels_in_the_text():
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    import pdfplumber
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(595, 842))
    pdf.drawString(72, 780, "The Pythagorean theorem relates the sides of a right triangle in this lesson.")
    pdf.drawImage(ImageReader(io.BytesIO(diagram_png())), 72, 420, width=400, height=240)
    pdf.save()
    with pdfplumber.open(io.BytesIO(buffer.getvalue())) as document:
        notes = figures.pdf_page_notes(document.pages[0], figures.Budget())
    assert len(notes) == 1 and "10 cm" in notes[0]
