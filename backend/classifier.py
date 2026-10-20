"""Works out what math topic an uploaded PDF/DOCX is about.

Three jobs, all built on rag.generate_text (so they use whichever model the app is
configured for: Groq, Hermes or local Ollama):

  * classify_branch    - Algebra / Geometry / Statistics / Calculus / not math (teacher + admin uploads)
  * check_relevance    - does this file belong to a given subject? (lesson generation)
  * summarize_document - a title + description for a new personal subject

The model is asked for plain "Label: number" lines instead of JSON, like the quiz generator,
because small local models break JSON and LaTeX backslashes.

rag.py is imported inside the functions on purpose: it pulls in Chroma/Ollama, and keeping
this module's import light is what lets the parsing code be tested without them.
"""
import json
import logging
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

import config

AUTO = "Auto"                      # the "detect it for me" choice in the upload form
NOT_MATH = "Not mathematics"
BRANCH_LABELS = ["Algebra", "Geometry", "Statistics", "Calculus"]

SYSTEM = (
    "You are a careful mathematics curriculum assistant. Follow the requested output format "
    "exactly and write nothing else. Never use emojis."
)


# ---------------------------------------------------------------- reading the file
def sample_text(text: str, limit: int | None = None) -> str:
    """A short, representative excerpt: mostly the start, plus a slice of the middle and the end."""
    limit = limit or config.CLASSIFY_SAMPLE_CHARS
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    head, mid = int(limit * 0.6), int(limit * 0.25)
    tail = limit - head - mid
    centre = len(text) // 2
    return f"{text[:head]} ... {text[centre - mid // 2: centre + mid // 2]} ... {text[-tail:]}"


def relevant_text(text: str, topic: str, limit: int = 8000, window: int = 1500) -> str:
    """The parts of a long document that mention `topic`'s words most, in document order, up to
    `limit` characters. Lets each lesson of a big PDF draw on its own pages instead of only page 1.
    ponytail: plain word-overlap scoring; upgrade to the Chroma embeddings if titles stop matching."""
    if len(text) <= limit:
        return text
    words = {w for w in re.findall(r"[a-z]{4,}", topic.lower())}
    windows = [(i, text[i:i + window]) for i in range(0, len(text), window)]
    scored = sorted(
        windows,
        key=lambda item: (-sum(item[1].lower().count(w) for w in words), item[0]),
    )
    chosen = sorted(scored[: max(1, limit // window)], key=lambda item: item[0])
    return "\n...\n".join(chunk for _, chunk in chosen)


def document_text(filename: str, contents: bytes) -> str:
    """All readable text of a pdf/docx/txt/md. Raises ValueError if it can't be read."""
    from rag import extract_text_from_bytes
    pages = extract_text_from_bytes(filename, contents)
    text = "\n\n".join("\n\n".join([page_text, *tables]) for _, page_text, tables in pages).strip()
    if not text:
        raise ValueError(f"No readable text found in {Path(filename).name} (scanned PDFs need OCR first)")
    return text


async def read_upload(file: UploadFile) -> tuple[str, str]:
    """(filename, text) for one uploaded file, or an HTTP 400/413 explaining why not."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="The uploaded file must have a filename")
    contents = await file.read()
    if len(contents) > config.MAX_ANALYZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File is too large (limit {config.MAX_ANALYZE_BYTES // 1024 // 1024} MB)")
    try:
        return file.filename, await run_in_threadpool(document_text, file.filename, contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------- topic of a document
def parse_scores(text: str) -> dict[str, float]:
    """'Algebra: 80' lines -> {label: share of the total}. Empty dict if nothing usable."""
    scores = {}
    for label in BRANCH_LABELS + [NOT_MATH]:
        match = re.search(rf"^\W*{re.escape(label)}\W*[:=\-]\s*(\d+(?:\.\d+)?)", text, re.I | re.M)
        if match:
            scores[label] = float(match.group(1))
    total = sum(scores.values())
    return {label: value / total for label, value in scores.items()} if total > 0 else {}


async def classify_branch(excerpt: str) -> dict:
    """{"branch", "confidence" (0-1), "scores", "reason"}. `reason` is None when the model is
    confident enough to proceed, else "low_confidence" / "not_math" / "unavailable"."""
    from rag import generate_text
    prompt = (
        "Decide which branch of school mathematics this document excerpt belongs to. Give your "
        "probability for each option as whole numbers that add up to 100.\n"
        "Algebra: equations, expressions, polynomials, functions, inequalities, sequences and series, matrices\n"
        "Geometry: shapes, angles, area and volume, proofs, coordinate geometry, trigonometry\n"
        "Statistics: data, probability, random variables, distributions, sampling, hypothesis testing\n"
        "Calculus: limits, derivatives, integrals, rates of change\n"
        "Not mathematics: the excerpt is not about school mathematics\n\n"
        "Reply with exactly these five lines and nothing else:\n"
        "Algebra: <number>\nGeometry: <number>\nStatistics: <number>\nCalculus: <number>\nNot mathematics: <number>\n\n"
        f'Document excerpt:\n"""\n{excerpt}\n"""'
    )
    try:
        scores = parse_scores(await generate_text(SYSTEM, prompt, "", ""))
    except Exception:
        return {"branch": None, "confidence": 0.0, "scores": {}, "reason": "unavailable"}
    if not scores:
        return {"branch": None, "confidence": 0.0, "scores": {}, "reason": "low_confidence"}
    top = max(scores, key=scores.get)
    reason = None
    if top == NOT_MATH:
        reason = "not_math"
    elif scores[top] < config.CLASSIFY_MIN_CONFIDENCE:
        reason = "low_confidence"
    return {"branch": None if top == NOT_MATH else top, "confidence": scores[top], "scores": scores, "reason": reason}


# ---------------------------------------------------------------- does it belong to this subject?
def _line_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\W*{key}\W*[:=\-]\s*(.+)$", text, re.I | re.M)
    return match.group(1).strip(" \t*_\"'`") if match else None


async def check_relevance(excerpt: str, subject_name: str, subject_description: str | None) -> dict:
    """{"relevance" (0-1), "detected_topic"}. A reply that can't be read counts as relevance 0,
    so the student gets the warning (and can still continue) rather than a silent pass."""
    from rag import generate_text
    about = f' ({subject_description.strip()})' if subject_description and subject_description.strip() else ""
    prompt = (
        f'A student is studying a subject called "{subject_name}"{about}. Decide whether the document '
        "excerpt below is about that subject.\n\n"
        "Reply with exactly these two lines and nothing else:\n"
        "DETECTED_TOPIC: <the document's main topic in 3 to 8 words>\n"
        "RELEVANCE: <whole number from 0 to 100: how likely the document belongs to the subject>\n\n"
        f'Document excerpt:\n"""\n{excerpt}\n"""'
    )
    reply = await generate_text(SYSTEM, prompt, "", "")
    number = re.search(r"\d+(?:\.\d+)?", _line_value(reply, "RELEVANCE") or "")
    relevance = min(float(number.group()), 100.0) / 100 if number else 0.0
    return {"relevance": relevance, "detected_topic": (_line_value(reply, "DETECTED_TOPIC") or "")[:120]}


# ---------------------------------------------------------------- which subject, or a new one?
def parse_subject_choice(reply: str, names: list[str]) -> dict:
    """Read the model's answer to choose_subject. {"action": existing|new|unclear|not_math,
    "subject": an existing name or None, "new_name", "description", "confidence" (0-1)}.
    A subject is only picked when the model is >= CLASSIFY_MIN_CONFIDENCE sure; a new name is
    only accepted when the model did not pick an existing subject."""
    lookup = {name.casefold(): name for name in names}
    wanted = (_line_value(reply, "SUBJECT") or "").strip(" .")
    number = re.search(r"\d+(?:\.\d+)?", _line_value(reply, "CONFIDENCE") or "")
    confidence = min(float(number.group()), 100.0) / 100 if number else 0.0
    new_name = re.sub(r"[$\\]", "", _line_value(reply, "NEW_NAME") or "").strip(" .")[:80]
    if new_name.casefold() in ("none", "n/a", "null"):   # the prompt tells the model to write NONE when there is no new branch
        new_name = ""
    result = {"action": "unclear", "subject": None, "new_name": None,
              "description": (_line_value(reply, "DESCRIPTION") or "")[:500], "confidence": confidence}
    if (_line_value(reply, "IS_MATH") or "yes").strip().lower().startswith("n"):
        return {**result, "action": "not_math"}
    match = lookup.get(wanted.casefold())
    if match:
        return {**result, "action": "existing" if confidence >= config.CLASSIFY_MIN_CONFIDENCE else "unclear", "subject": match}
    if new_name:
        same = lookup.get(new_name.casefold())   # the model "invented" a name we already have
        return {**result, "action": "existing", "subject": same} if same else {**result, "action": "new", "new_name": new_name}
    return result


async def choose_subject(excerpt: str, subjects: list[tuple[str, str | None]]) -> dict:
    """Which existing subject does this document belong to, or is it a new branch of math?
    `subjects` is [(name, description)]. See parse_subject_choice for the result."""
    from rag import generate_text
    listing = "\n".join(
        f"- {name}" + (f": {desc.strip()}" if desc and desc.strip() else "") for name, desc in subjects
    ) or "(none yet)"
    prompt = (
        "A math learning app has these subjects:\n"
        f"{listing}\n\n"
        "Decide which subject the document excerpt below belongs to. If it is school mathematics but "
        "clearly fits none of them, answer NEW and name the branch it belongs to (for example "
        "Trigonometry, Number Theory, Linear Algebra, Discrete Mathematics).\n\n"
        "Reply with exactly these five lines and nothing else:\n"
        "IS_MATH: <YES or NO>\n"
        "SUBJECT: <one subject name copied exactly from the list, or NEW>\n"
        "CONFIDENCE: <whole number 0 to 100: how sure you are of SUBJECT>\n"
        "NEW_NAME: <2 to 4 word plain-text name of the new branch if SUBJECT is NEW, otherwise NONE>\n"
        "DESCRIPTION: <one sentence, at most 200 characters, saying what the branch covers>\n\n"
        f'Document excerpt:\n"""\n{excerpt}\n"""'
    )
    reply = await generate_text(SYSTEM, prompt, "", "")
    return parse_subject_choice(reply, [name for name, _ in subjects])


# ---------------------------------------------------------------- title + description
async def summarize_document(excerpt: str) -> tuple[str, str]:
    """(title <= 80 chars, description <= 500 chars) for a subject or lesson, from the file's content."""
    from rag import generate_text
    prompt = (
        "Read the document excerpt and write a short title and description for a study subject "
        "about it.\n\nReply with exactly these two lines and nothing else:\n"
        "TITLE: <at most 6 words, no quotes>\n"
        "DESCRIPTION: <one or two sentences, at most 300 characters, saying what a student will learn>\n\n"
        f'Document excerpt:\n"""\n{excerpt}\n"""'
    )
    reply = await generate_text(SYSTEM, prompt, "", "")
    title, description = _line_value(reply, "TITLE"), _line_value(reply, "DESCRIPTION")
    if not title:
        raise ValueError("The model's title could not be read")
    return title[:80], (description or "")[:500]


# ---------------------------------------------------------------- admin + teacher upload
async def ingest_with_detection(files: list[UploadFile], branch: str, branches_json: str, username: str, db, school_id=None) -> dict:
    """Shared body of /admin/upload and /teacher/upload.

    `branch` is a real branch (as before) or AUTO. Under AUTO each file is classified; files the
    model is >= CLASSIFY_MIN_CONFIDENCE sure about are saved under their branch, the rest are NOT
    saved and come back in `needs_topic` so the uploader can pick. `branches_json` is that pick:
    {"file name": "Algebra"}, sent when the uploader re-submits those files.
    """
    from models import Material
    from notifications import notify_admins
    from progress import UPLOAD_BRANCHES
    from rag import ingest_uploaded_materials

    if branch != AUTO and branch not in UPLOAD_BRANCHES:
        raise HTTPException(status_code=400, detail=f"Branch must be one of: {', '.join([AUTO, *UPLOAD_BRANCHES])}")
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one file to upload")
    try:
        picked = json.loads(branches_json) if branches_json else {}
    except ValueError:
        picked = None
    if not isinstance(picked, dict) or any(value not in UPLOAD_BRANCHES for value in picked.values()):
        raise HTTPException(status_code=400, detail=f"Chosen topics must be one of: {', '.join(UPLOAD_BRANCHES)}")

    ready: dict[str, list[tuple[str, bytes]]] = {}   # branch -> files to save
    detected: dict[str, float] = {}                  # file name -> confidence, for auto-detected files
    needs_topic = []
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Every uploaded file must have a filename")
        contents = await file.read()
        target = picked.get(file.filename) or (branch if branch != AUTO else None)
        if target is None:
            try:
                text = await run_in_threadpool(document_text, file.filename, contents)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            result = await classify_branch(sample_text(text))
            if result["reason"] is None:
                target = result["branch"]
                detected[file.filename] = result["confidence"]
            else:
                label = f"{result['branch']} ({round(result['confidence'] * 100)}%)" if result["branch"] else "no clear topic"
                why = {"not_math": "it doesn't look like a math document", "unavailable": "the AI couldn't analyze it"}.get(result["reason"], f"the AI wasn't confident enough, best guess: {label}")
                notify_admins(db, "needs_topic", "AI needs help filing a file", f'@{username} uploaded "{file.filename}" but {why}. Waiting for a topic to be chosen.')
                needs_topic.append({
                    "filename": file.filename,
                    "guess": result["branch"],
                    "confidence": round(result["confidence"], 2),
                    "reason": result["reason"],
                })
                continue
        ready.setdefault(target, []).append((file.filename, contents))

    uploaded = []
    for target, group in ready.items():
        try:
            stored = await run_in_threadpool(ingest_uploaded_materials, group, target)
        except (ValueError, FileNotFoundError) as exc:
            db.commit()   # keep the records of groups that were already saved
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            # Without this, the error escapes as a bare 500 that carries no CORS headers, and the
            # browser can only report "Failed to fetch". An HTTPException reaches the page intact.
            db.commit()
            logging.getLogger(__name__).exception("Upload failed while saving/indexing")
            raise HTTPException(status_code=502, detail=f"The upload failed: {str(exc)[:200]}") from exc
        for (original_name, _), stored_path in zip(group, stored):
            db.add(Material(
                filename=str(stored_path),
                display_name=Path(original_name.replace("\\", "/")).name,
                branch=target,
                uploaded_by=username,
                school_id=school_id,
                drive_file_id=getattr(stored_path, "drive_file_id", None),   # set when the original went to Google Drive
            ))
            if original_name in picked:   # the AI wasn't sure, so a person chose the topic
                notify_admins(db, "manual_topic", "Topic chosen by a person",
                              f'@{username} filed "{original_name}" under {target} after the AI wasn\'t sure.')
            else:
                how = f"The AI filed it under {target} ({round(detected[original_name] * 100)}% sure)." if original_name in detected else f"Filed under {target}."
                notify_admins(db, "upload", "New file uploaded", f'@{username} uploaded "{original_name}". {how}', exclude=username)
            uploaded.append({
                "filename": original_name,
                "branch": target,
                "auto_detected": original_name in detected,
                "confidence": round(detected[original_name], 2) if original_name in detected else None,
            })
    db.commit()

    message = ""
    if uploaded:
        message = f"Saved and indexed {len(uploaded)} file(s) under {', '.join(sorted(ready))}."
    if needs_topic:
        message = f"{message} {len(needs_topic)} file(s) need a topic before they can be saved.".strip()
    return {"message": message, "uploaded": uploaded, "needs_topic": needs_topic}
