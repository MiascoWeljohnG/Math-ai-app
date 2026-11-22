"""Figures inside documents: diagrams, graphs and geometry drawings.

Pictures embedded in a PDF / DOCX / PPTX are not text, so reading the text layer skips them. For each real figure this
adds, to the page's text:
  * the words printed inside it (OCR), such as labels, axis names and measurements, and
  * if a vision model is configured (Groq, with an Ollama model as the reserve), a short description of what it shows.
Everything is optional and best effort: a failure here never stops the file from being read.
"""
import base64
import hashlib
import io
import logging
import time

import httpx

import config
import ocr

log = logging.getLogger("figures")

PROMPT = (
    "This figure comes from a mathematics lesson. Describe it in one to three short sentences for a student who cannot "
    "see it: the kind of figure (triangle, graph, number line, table, circle, diagram...), the labelled values, angles, "
    "lengths, axes or points, and how they relate. Do not solve anything and do not add information that is not shown. "
    "If it is only decoration, a logo or a photo with no mathematical content, answer exactly: NONE"
)


class Budget:
    """What one file may spend, and the images already seen (a logo repeated on every slide is described once)."""
    def __init__(self):
        self.vision_left = config.FIGURE_MAX_VISION
        self.ocr_left = config.FIGURE_MAX_OCR
        self.seen: dict[str, int] = {}

    def repeated(self, blob: bytes) -> bool:
        key = hashlib.sha1(blob).hexdigest()
        self.seen[key] = self.seen.get(key, 0) + 1
        return self.seen[key] > 1   # the same picture again: a logo or a background


def _groq_on() -> bool:
    return bool(config.GROQ_API_KEY and config.GROQ_VISION_MODEL)


def _ollama_on() -> bool:
    return bool(config.OLLAMA_BASE_URL and config.OLLAMA_VISION_MODEL)


def _vision_on() -> bool:
    return bool(config.FIGURE_DESCRIPTIONS and (_groq_on() or _ollama_on()))


# When a provider says "no more for now" it is skipped until this time, so the figures after it don't each wait.
_groq_paused_until = 0.0
_ollama_paused_until = 0.0
_ollama_failures = 0


def _png(image) -> bytes:
    """A PIL image as PNG bytes, shrunk so the request stays small."""
    from PIL import Image
    image = image.convert("RGB")
    if max(image.size) > 1024:
        scale = 1024 / max(image.size)
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _describe(image) -> str:
    """A short description of one figure: Groq vision first, and the Ollama model as the reserve when Groq is out of
    quota, rate limited or failing. '' when there is nothing worth saying, or when nothing could answer."""
    png = _png(image)
    text = None   # None = no answer yet; '' = answered with nothing
    if _groq_on() and time.time() >= _groq_paused_until:
        text = _describe_groq(png)
    if text is None and _ollama_on():
        text = _describe_ollama(png)
    return "" if not text or text.upper().startswith("NONE") else " ".join(text.split())


def _describe_groq(png: bytes) -> str | None:
    """One Groq vision call: the description, or None when Groq couldn't answer (the reserve is tried next)."""
    global _groq_paused_until
    body = {
        "model": config.GROQ_VISION_MODEL,
        "max_tokens": 220,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
        ]}],
    }
    url = f"{config.GROQ_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
    try:
        with httpx.Client(timeout=60) as client:
            for attempt in range(3):
                response = client.post(url, headers=headers, json=body)
                if response.status_code in (429, 503) and attempt < 2:
                    try:
                        wait = float(response.headers.get("retry-after", ""))
                    except ValueError:
                        wait = 2 ** attempt
                    if wait > 10 and _ollama_on():   # a long wait (the quota is used up): don't sit through it, use the reserve
                        _groq_paused_until = time.time() + min(wait, 3600)
                        log.warning("Groq vision is limited for %.0fs; using the Ollama reserve", wait)
                        return None
                    time.sleep(min(wait, 10))
                    continue
                response.raise_for_status()
                return (response.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503):
            _groq_paused_until = time.time() + 60   # kept answering "busy": leave it alone for a minute
        log.warning("figure description (Groq) failed: %s", exc)
    return None


def _describe_ollama(png: bytes) -> str | None:
    """One call to the reserve vision model on an Ollama server: the description, or None if it couldn't answer.
    Two failures in a row (computer off, tunnel closed, too slow) pause it for five minutes so a file isn't held up."""
    global _ollama_paused_until, _ollama_failures
    if time.time() < _ollama_paused_until:
        return None
    base = config.OLLAMA_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    body = {
        "model": config.OLLAMA_VISION_MODEL,
        "stream": False,
        "think": False,   # answer straight away instead of spending the reply on thinking
        "options": {"temperature": 0, "num_predict": 300},
        "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(png).decode()]}],
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(config.OLLAMA_VISION_TIMEOUT, connect=8)) as client:
            response = client.post(f"{base}/api/chat", json=body)
            response.raise_for_status()
            text = (response.json().get("message", {}).get("content") or "").strip()
    except Exception as exc:
        _ollama_failures += 1
        if _ollama_failures >= 2:
            _ollama_paused_until = time.time() + 300
            _ollama_failures = 0
            log.warning("Ollama vision failed twice in a row (%s); pausing it for 5 minutes", exc)
        else:
            log.warning("figure description (Ollama) failed: %s", exc)
        return None
    _ollama_failures = 0
    return text


def figure_note(image, budget: Budget) -> str:
    """'[Figure: description. Text in the figure: ...]' for one PIL image, or '' when there is nothing to add."""
    labels = description = ""
    if config.FIGURE_OCR and budget.ocr_left > 0:
        budget.ocr_left -= 1
        try:
            labels = " ".join(ocr.ocr_image(image).split())
        except ocr.OcrUnavailable:
            budget.ocr_left = 0
        except Exception as exc:
            log.warning("figure OCR failed: %s", exc)
    if _vision_on() and budget.vision_left > 0:
        budget.vision_left -= 1
        description = _describe(image)
    if not labels and not description:
        return ""
    parts = [description.rstrip(".")] if description else []
    if labels:
        parts.append(f"Text in the figure: {labels}")
    return "[Figure: " + ". ".join(parts) + "]"


def _usable(width: float, height: float) -> bool:
    """Big enough to be a figure (not an icon or bullet) and not a thin line."""
    size = config.FIGURE_MIN_PX
    return width >= size and height >= size and max(width, height) / max(min(width, height), 1) <= 8


# ---------------------------------------------------------------- PDF
def pdf_page_notes(page, budget: Budget) -> list[str]:
    """Notes for the figures drawn on one pdfplumber page (pictures, or a cluster of drawn lines and curves)."""
    notes = []
    page_area = float(page.width * page.height)
    try:
        regions = []
        for picture in page.images:
            w, h = picture["x1"] - picture["x0"], picture["bottom"] - picture["top"]
            if w * h > 0.8 * page_area:   # the whole page is one picture: a scan, which OCR already read
                continue
            if _usable(w * 150 / 72, h * 150 / 72):   # points -> pixels at 150 dpi
                regions.append((picture["x0"], picture["top"], picture["x1"], picture["bottom"]))
        if not regions:   # a drawing made of lines and curves has no picture object: take their joint box
            shapes = list(page.curves) + list(page.lines)
            if len(shapes) >= 25:
                x0, x1 = min(s["x0"] for s in shapes), max(s["x1"] for s in shapes)
                top, bottom = min(s["top"] for s in shapes), max(s["bottom"] for s in shapes)
                if _usable((x1 - x0) * 150 / 72, (bottom - top) * 150 / 72) and (x1 - x0) * (bottom - top) < 0.8 * page_area:
                    regions.append((x0, top, x1, bottom))
        for box in regions[:6]:   # at most six figures on one page
            box = (max(box[0], 0), max(box[1], 0), min(box[2], page.width), min(box[3], page.height))
            image = page.crop(box).to_image(resolution=150).original
            if budget.repeated(image.tobytes()[:200000]):
                continue
            note = figure_note(image, budget)
            if note:
                notes.append(note)
    except Exception as exc:   # never let a drawing problem stop the text from being read
        log.warning("figures on a PDF page failed: %s", exc)
    return notes


# ---------------------------------------------------------------- DOCX / PPTX
def blob_note(blob: bytes, budget: Budget) -> str:
    """Note for one embedded image file (its bytes); '' for icons, repeats, unreadable or unsupported images."""
    try:
        from PIL import Image
        if budget.repeated(blob):
            return ""
        with Image.open(io.BytesIO(blob)) as image:
            if not _usable(*image.size):
                return ""
            image.load()
            return figure_note(image, budget)
    except Exception as exc:   # EMF/WMF and other formats Pillow cannot open
        log.info("embedded image skipped: %s", exc)
        return ""


def docx_notes(document, budget: Budget) -> list[str]:
    notes = []
    for part in document.part.related_parts.values():
        if getattr(part, "content_type", "").startswith("image/"):
            note = blob_note(part.blob, budget)
            if note:
                notes.append(note)
    return notes


def pptx_slide_notes(slide, budget: Budget) -> list[str]:
    notes = []
    for shape in slide.shapes:
        if getattr(shape, "shape_type", None) == 13:   # MSO_SHAPE_TYPE.PICTURE
            try:
                note = blob_note(shape.image.blob, budget)
            except Exception:
                note = ""
            if note:
                notes.append(note)
    return notes
