"""OCR for scanned PDFs and photos (ocr.py). Skipped when the OCR package is not installed."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("rapidocr_onnxruntime")
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import ocr  # noqa: E402


def sample_png(lines=("Sine of 225 degrees", "Chapter 3 Linear Equations")) -> bytes:
    image = Image.new("RGB", (1000, 100 + 90 * len(lines)), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:   # very old Pillow
        font = ImageFont.load_default()
    for i, line in enumerate(lines):
        draw.text((40, 40 + 90 * i), line, fill="black", font=font)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_a_photo_is_read_line_by_line_in_reading_order():
    text = ocr.ocr_image_bytes(sample_png())
    assert text.splitlines()[0].lower().startswith("sine of 225")
    assert "linear equations" in text.lower().replace("3", "").replace(":", "")


def test_a_photo_becomes_a_one_page_pdf_whose_picture_can_be_read():
    pdf = ocr.image_to_pdf(sample_png())
    assert pdf.startswith(b"%PDF")
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        assert len(document.pages) == 1
        assert not (document.pages[0].extract_text() or "").strip()   # a scan: no text layer
        assert "225" in ocr.ocr_pdf_page(document.pages[0])


def test_a_blank_page_gives_no_text():
    blank = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(blank, "PNG")
    assert ocr.ocr_image_bytes(blank.getvalue()).strip() == ""


def test_boxes_on_one_row_are_joined_left_to_right_and_weak_guesses_dropped():
    box = lambda x, y: [[x, y], [x + 50, y], [x + 50, y + 20], [x, y + 20]]
    result = [(box(200, 10), "world", 0.99), (box(10, 12), "hello", 0.98), (box(10, 80), "next line", 0.97), (box(300, 80), "noise", 0.1)]
    assert ocr._lines(result) == "hello world\nnext line"
