"""Reading scans: scanned PDF pages and photos of pages.

No OCR engine runs on this server (those engines use a lot of memory). A page that has no text layer is drawn as a
picture and sent to a vision model that copies the text out of it. The models are tried in turn, and each one is only
used when it is set up:

    1. Groq     GROQ_API_KEY + GROQ_VISION_MODEL
    2. Gemini   GEMINI_API_KEY (the model is GEMINI_VISION_MODEL, or GEMINI_MODEL when that is not set)
    3. Ollama   OLLAMA_BASE_URL + OLLAMA_VISION_MODEL (a model on your own computer, reached through a tunnel)

OCR_PROVIDERS changes the order or leaves some out, for example OCR_PROVIDERS=groq,ollama.

A provider that says "no more for now" (rate limit) or that can't be reached is skipped for a while, so the pages after
it don't each wait. When no provider can read a page, OcrUnavailable is raised with the reason.
"""
import base64
import io
import json
import logging
import os
import re
import time

import httpx

import config

log = logging.getLogger("ocr")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "40"))      # scanned pages read per file (each page is one vision call)
DPI = int(os.getenv("OCR_DPI", "150"))                 # how sharply a PDF page is drawn before it is read
MAX_SIDE = int(os.getenv("OCR_MAX_SIDE", "2000"))      # larger pictures are shrunk to this, to keep the request small
JPEG_QUALITY = 85
MAX_TOKENS = int(os.getenv("OCR_MAX_TOKENS", "3000"))  # the longest transcription asked for, per page
OLLAMA_TIMEOUT = int(os.getenv("OCR_OLLAMA_TIMEOUT", "180"))   # seconds one page may take on the Ollama computer
PROVIDERS = [name.strip().lower() for name in os.getenv("OCR_PROVIDERS", "groq,gemini,ollama").split(",") if name.strip()]

PROMPT = (
    "Transcribe all the text on this page exactly as written, in reading order, one line of text per line. "
    "Keep numbers, units, percent signs and math symbols exactly as shown. Write mathematical expressions in plain "
    "text (for example 3/4, x^2, 25%), and use LaTeX only when plain text would be ambiguous. Write a table as one "
    "row per line with ' | ' between the cells. For a figure or diagram, copy only the text labels inside it. "
    "Do not describe the picture, do not summarise, do not solve anything and do not add comments or code fences. "
    "If a word or number cannot be read, write [unclear] instead of guessing. "
    "If the page has no text at all, answer exactly: NONE"
)


class OcrUnavailable(RuntimeError):
    """No vision model could read the page (none is set up, or they are busy or unreachable)."""


# provider name -> time until which it is skipped (it said "slow down", or it is misconfigured)
_paused_until: dict[str, float] = {}
_ollama_failures = 0


def _gemini_model() -> str:
    return os.getenv("GEMINI_VISION_MODEL", "").strip() or config.GEMINI_MODEL


def _enabled(name: str) -> bool:
    if name == "groq":
        return bool(config.GROQ_API_KEY and config.GROQ_VISION_MODEL)
    if name == "gemini":
        return bool(config.GEMINI_API_KEY and _gemini_model())
    if name == "ollama":
        return bool(config.OLLAMA_BASE_URL and config.OLLAMA_VISION_MODEL)
    return False


def available() -> bool:
    return any(_enabled(name) for name in PROVIDERS)


def _retry_after(response, default: float) -> float:
    try:
        return float(response.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return default


def _chat_openai(name: str, base_url: str, key: str, model: str, b64: str) -> str | None:
    """One call to an OpenAI-style vision endpoint (Groq, or Gemini's compatible endpoint): the page text, or None
    when this provider couldn't answer (the next one is tried)."""
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]}],
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {key}"}
    try:
        with httpx.Client(timeout=90) as client:
            for attempt in range(3):
                response = client.post(url, headers=headers, json=body)
                if response.status_code in (429, 503):
                    wait = _retry_after(response, 2 ** attempt)
                    if wait > 20 or attempt == 2:   # a long wait (quota used up) or still busy: leave it alone for a while
                        _paused_until[name] = time.time() + min(max(wait, 60), 3600)
                        log.warning("%s is limited or busy; skipping it for a while", name)
                        return None
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403, 404):
            _paused_until[name] = time.time() + 600   # a wrong key or model name: no point asking again for every page
        log.warning("reading a scan with %s failed: %s", name, exc)
    return None


def _chat_ollama(b64: str) -> str | None:
    """One call to the Ollama vision model. The answer is streamed, so a slow page doesn't hit the tunnel's time limit.
    Two failures in a row (computer off, tunnel closed) pause it for five minutes so a file isn't held up."""
    global _ollama_failures
    base = config.OLLAMA_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    body = {
        "model": config.OLLAMA_VISION_MODEL,
        "stream": True,
        "think": False,   # answer straight away instead of spending the reply on thinking
        "options": {"temperature": 0, "num_predict": MAX_TOKENS},
        "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
    }
    deadline = time.time() + OLLAMA_TIMEOUT
    try:
        parts: list[str] = []
        with httpx.Client(timeout=httpx.Timeout(90, connect=8)) as client:
            with client.stream("POST", f"{base}/api/chat", json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if time.time() > deadline:
                        raise TimeoutError(f"the page took longer than {OLLAMA_TIMEOUT}s")
                    if not line:
                        continue
                    piece = json.loads(line)
                    if piece.get("error"):
                        raise RuntimeError(piece["error"])
                    parts.append((piece.get("message") or {}).get("content") or "")
                    if piece.get("done"):
                        break
        _ollama_failures = 0
        return "".join(parts)
    except Exception as exc:
        _ollama_failures += 1
        if _ollama_failures >= 2:
            _paused_until["ollama"] = time.time() + 300
            _ollama_failures = 0
            log.warning("Ollama failed twice in a row (%s); pausing it for 5 minutes", exc)
        else:
            log.warning("reading a scan with Ollama failed: %s", exc)
    return None


def _call(name: str, b64: str) -> str | None:
    if name == "groq":
        return _chat_openai("groq", config.GROQ_BASE_URL, config.GROQ_API_KEY, config.GROQ_VISION_MODEL, b64)
    if name == "gemini":
        return _chat_openai("gemini", config.GEMINI_BASE_URL, config.GEMINI_API_KEY, _gemini_model(), b64)
    return _chat_ollama(b64)


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"^```[A-Za-z]*\n(.*?)\n?```$", re.S)


def _clean(text: str) -> str:
    """The model's answer as plain page text: no reasoning block, no code fence, and '' for 'NONE' (no text on the page)."""
    text = _THINK.sub("", text).strip()
    fence = _FENCE.match(text)
    if fence:
        text = fence.group(1).strip()
    if text.rstrip(". ").upper() == "NONE":
        return ""
    return text


def _read(b64: str) -> str:
    candidates = [name for name in PROVIDERS if _enabled(name)]
    if not candidates:
        raise OcrUnavailable("No vision model is set up to read scans (set GROQ_VISION_MODEL with GROQ_API_KEY, "
                             "or GEMINI_API_KEY, or OLLAMA_BASE_URL with OLLAMA_VISION_MODEL).")
    for name in candidates:
        if time.time() < _paused_until.get(name, 0):
            continue
        text = _call(name, b64)
        if text is not None:
            return _clean(text)
    raise OcrUnavailable("The AI models that read scans are busy or can't be reached right now. Try again in a few "
                         "minutes, or upload a PDF whose text can be selected.")


def ocr_image(image) -> str:
    """Text of a PIL image. Raises OcrUnavailable when no vision model could read it."""
    from PIL import Image
    image = image.convert("RGB")
    if image.convert("L").getextrema()[0] >= 240:   # an all-white page: nothing to read, and no call to spend
        return ""
    longest = max(image.size)
    if longest > MAX_SIDE:
        scale = MAX_SIDE / longest
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=JPEG_QUALITY)
    return _read(base64.b64encode(out.getvalue()).decode())


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
