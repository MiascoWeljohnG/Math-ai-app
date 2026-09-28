from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User, Conversation, ChatMessage
from rag import ask, queue_status
from progress import progress_for_user

router = APIRouter(tags=["user"])


class Question(BaseModel):
    question: str
    # Which conversation this message belongs to. Omit it to start a new one
    # (the frontend does this the first time a user sends a message in a
    # fresh tab).
    conversation_id: Optional[int] = None
    # The file open in the materials viewer, if the question comes from
    # there. Limits the AI's reference material to that document.
    material_filename: Optional[str] = None


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
    return [{"role": m.role, "content": m.content} for m in messages]


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
def get_progress(user: User = Depends(get_current_user)):
    return progress_for_user(user.username)


@router.post("/ask")
async def ask_question(
    req: Question,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Resolve which conversation this belongs to, creating one if this is
    # the first message in a brand-new tab.
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
    history = [{"role": m.role, "content": m.content} for m in prior_messages]

    # Save the user's message immediately, before calling the AI, so it's
    # never lost even if the request below times out.
    db.add(ChatMessage(conversation_id=convo.id, role="user", content=req.question))
    if convo.title == "New chat":
        convo.title = req.question[:60] + ("…" if len(req.question) > 60 else "")
    db.commit()

    result = await ask(req.question, chat_history=history, material_filename=req.material_filename)

    db.add(ChatMessage(conversation_id=convo.id, role="assistant", content=result["answer"]))
    db.commit()

    return {
        "answer": result["answer"],
        "was_queued": result["was_queued"],
        "queue_position": result["queue_position"],
        "conversation_id": convo.id,
        "conversation_title": convo.title,
    }
