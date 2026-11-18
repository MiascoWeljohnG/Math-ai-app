"""OCR (optical character recognition) for uploads: scanned PDFs and photos of pages.

Uses RapidOCR (pip only, runs on the CPU, no system packages), so it works on a plain Render instance. The engine is
loaded the first time it is needed and kept, because loading it is the slow part. If the package is missing the rest
of the app keeps working; only scanned files are refused, with a message that says why.
"""
import io
import logging
import os
import threading

log = logging.getLogger("ocr")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "120"))   # scanned pages read per file (a page takes a second or two)
DPI = int(os.getenv("OCR_DPI", "170"))               # how sharply a PDF page is drawn before it is read
MAX_SIDE = 2600                                      # larger photos are shrunk to this, for speed and memory
MIN_CONFIDENCE = 0.45                                # words the engine is less sure of than this are dropped

_engine = None
_lock = threading.Lock()   # one page at a time: the engine is not meant to be shared between threads


class OcrUnavailable(RuntimeError):
    """The OCR package is not installed (or failed to start) on this server."""


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        except Exception as exc:   # ImportError, or the model files failed to load
            raise OcrUnavailable(f"OCR is not available on this server ({exc}).") from exc
    return _engine


def available() -> bool:
    try:
        _get_engine()
        return True
    except OcrUnavailable:
        return False


def _lines(boxes) -> str:
    """Engine results [(box, text, score)] -> text in reading order: boxes on the same row are joined left to right."""
    items = []
    for box, text, score in boxes:
        if not text or float(score) < MIN_CONFIDENCE:
            continue
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        items.append({"x": min(xs), "y": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys), "text": text.strip()})
    items.sort(key=lambda item: item["y"])
    rows: list[list[dict]] = []
    for item in items:
        if rows and abs(item["y"] - rows[-1][-1]["y"]) <= 0.6 * max(item["h"], 1):
            rows[-1].append(item)
        else:
            rows.append([item])
    return "\n".join(" ".join(part["text"] for part in sorted(row, key=lambda part: part["x"])) for row in rows)


def ocr_image(image) -> str:
    """Text of a PIL image. Raises OcrUnavailable when the engine is missing."""
    import numpy as np
    from PIL import Image
    engine = _get_engine()
    image = image.convert("RGB")
    longest = max(image.size)
    if longest > MAX_SIDE:
        scale = MAX_SIDE / longest
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.LANCZOS)
    with _lock:
        result, _ = engine(np.array(image))
    return _lines(result or [])


def ocr_image_bytes(contents: bytes) -> str:
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(contents)) as image:
        return ocr_image(ImageOps.exif_transpose(image))   # phone photos carry their rotation in EXIF


def ocr_pdf_page(page) -> str:
    """Text of one pdfplumber page that has no text layer (a scan)."""
    rendered = page.to_image(resolution=DPI)
    try:
        return ocr_image(rendered.original)
    finally:
        page.flush_cache()


def image_to_pdf(contents: bytes) -> bytes:
    """A photo or scan as a one-page PDF, so the rest of the app (viewer, page ranges, lessons) treats it like any PDF."""
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(contents)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        out = io.BytesIO()
        image.save(out, "PDF", resolution=float(DPI))
    return out.getvalue()
