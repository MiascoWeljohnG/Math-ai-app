import json
import base64
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, SessionLocal
from models import User, Conversation, ChatMessage, Material
from rag import ask_stream, queue_status
from progress import progress_for_user
from school import in_school

router = APIRouter(tags=["user"])

MAX_CHAT_IMAGES = 4
MAX_CHAT_IMAGE_CHARS = 12_000_000
ALLOWED_CHAT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class Question(BaseModel):
    question: str
    # Which conversation this message belongs to. Omit it to start a new one
    # (the frontend does this the first time a user sends a message in a
    # fresh tab).
    conversation_id: Optional[int] = None
    # The file open in the materials viewer, if the question comes from
    # there. Limits the AI's reference material to that document.
    material_filename: Optional[str] = None
    # Base64-encoded images (no "data:image/..." prefix) the student attached
    # to this question — e.g. a photo of handwritten work or a diagram.
    images: Optional[list[str]] = None
    image_mime_types: Optional[list[str]] = None


def _validate_images(req: Question) -> list[dict]:
    images = req.images or []
    mime_types = req.image_mime_types or [None] * len(images)
    if len(images) > MAX_CHAT_IMAGES:
        raise HTTPException(status_code=413, detail=f"Attach no more than {MAX_CHAT_IMAGES} images")
    if len(mime_types) != len(images):
        raise HTTPException(status_code=400, detail="Image data and image types do not match")
    if sum(len(image) for image in images) > MAX_CHAT_IMAGE_CHARS:
        raise HTTPException(status_code=413, detail="Attached images exceed the size limit")

    records = []
    for image, mime_type in zip(images, mime_types):
        try:
            decoded = base64.b64decode(image, validate=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid image data") from exc
        if decoded.startswith(b"\x89PNG\r\n\x1a\n"):
            detected_type = "image/png"
        elif decoded.startswith(b"\xff\xd8\xff"):
            detected_type = "image/jpeg"
        elif decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP":
            detected_type = "image/webp"
        else:
            detected_type = None
        if detected_type not in ALLOWED_CHAT_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Use a JPEG, PNG, or WebP image")
        if mime_type is not None and mime_type != detected_type:
            raise HTTPException(status_code=400, detail="Image type does not match its data")
        mime_type = detected_type
        records.append({"data": image, "mime_type": mime_type})
    return records


def _message_images(image_data: Optional[str], *, as_data_urls: bool = False) -> list:
    if not image_data:
        return []
    records = json.loads(image_data)
    if as_data_urls:
        return [f"data:{item['mime_type']};base64,{item['data']}" for item in records]
    return records


def _serialize_conversation(c: Conversation) -> dict:
    return {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()}


@router.get("/conversations")
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convos = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        # NEW: Filter out any conversation generated in the materials viewer
        .filter(~Conversation.title.like("__MAT__%"))
        .order_by(Conversation.id.desc())
        .all()
    )
    return [_serialize_conversation(c) for c in convos]

@router.post("/conversations")
def create_conversation(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = Conversation(user_id=user.id, title="New chat")
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return _serialize_conversation(convo)


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    return [
        {
            "role": m.role,
            "content": m.content,
            "images": _message_images(m.image_data, as_data_urls=True),
        }
        for m in messages
    ]


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id).delete()
    db.delete(convo)
    db.commit()
    return {"message": "Conversation deleted."}


@router.get("/queue-status")
def get_queue_status(user: User = Depends(get_current_user)):
    return queue_status()


@router.get("/progress")
def get_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return progress_for_user(db, user)


@router.post("/ask")
async def ask_question(
    req: Question,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Streams the answer back as newline-delimited JSON (NDJSON) instead of
    waiting for the whole response and sending it as one block — this is
    what makes the chat feel real-time instead of silence followed by a
    sudden wall of text. Total generation time is the same either way; the
    student just sees it happening instead of staring at dots for a minute.

    Each line is one JSON object:
      {"type": "meta", "conversation_id": ..., "conversation_title": ..., "was_queued": ..., "queue_position": ...}
      {"type": "token", "text": "..."}            — repeated, as generated
      {"type": "done"}                             — once, last
      {"type": "error", "detail": "..."}           — only if something broke mid-stream
    """
    image_records = _validate_images(req)
    if req.material_filename and not db.query(Material).filter(
        Material.filename == req.material_filename, in_school(Material.school_id, user.school_id),
    ).first():
        raise HTTPException(status_code=404, detail="File not found")   # another school's file
    # Resolve which conversation this belongs to, creating one if this is
    # the first message in a brand-new tab. This part runs before any
    # streaming starts, so using the normal injected `db` session is safe.
    convo = None
    if req.conversation_id is not None:
        convo = (
            db.query(Conversation)
            .filter(Conversation.id == req.conversation_id, Conversation.user_id == user.id)
            .first()
        )
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
    if convo is None:
        convo = Conversation(user_id=user.id, title="New chat")
        db.add(convo)
        db.commit()
        db.refresh(convo)

    # History comes from the database, not from whatever the browser has in
    # memory — this is what makes it survive a refresh, a logout, or opening
    # the same conversation on a different device.
    prior_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == convo.id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    history = [
        {
            "role": m.role,
            "content": m.content,
            "images": _message_images(m.image_data),
        }
        for m in prior_messages
    ]
# Save the user's message immediately, before calling the AI, so it's
    # never lost even if generation below fails partway through.
    db.add(ChatMessage(
        conversation_id=convo.id,
        role="user",
        content=req.question,
        image_data=json.dumps(image_records) if image_records else None,
    ))
    
    # NEW: Tag material conversations so the sidebar ignores them
    if convo.title == "New chat":
        if req.material_filename:
            convo.title = f"__MAT__{req.material_filename}"
        else:
            convo.title = req.question[:60] + ("…" if len(req.question) > 60 else "")
            
    db.commit()
    convo_id, convo_title = convo.id, convo.title  # capture before db may close
    async def event_stream():
        full_answer = ""
        try:
            async for event in ask_stream(
                req.question,
                chat_history=history,
                material_filename=req.material_filename,
                images=req.images,
            ):
                if event["type"] == "meta":
                    event["conversation_id"] = convo_id
                    event["conversation_title"] = convo_title
                elif event["type"] == "done":
                    full_answer = event["answer"]
                    del event["answer"]  # frontend already has the full text from the token events
                yield json.dumps(event) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"
            return

        # The route's own `db` session may already be closed by the time this
        # generator runs (StreamingResponse keeps iterating after the route
        # function returns) — open an independent one just for this save.
        save_db = SessionLocal()
        try:
            save_db.add(ChatMessage(conversation_id=convo_id, role="assistant", content=full_answer))
            save_db.commit()
        finally:
            save_db.close()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
