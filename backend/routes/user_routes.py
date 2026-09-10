from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from auth import get_current_user
from models import User
from rag import ask, queue_status, QueueTimeoutError

router = APIRouter(tags=["user"])

class ChatMessage(BaseModel):
    role: str
    content: str

class Question(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None

@router.get("/queue-status")
def get_queue_status(user: User = Depends(get_current_user)):
    return queue_status()

@router.post("/ask")
async def ask_question(
    req: Question,
    user: User = Depends(get_current_user),
):
    history = None
    if req.history:
        history = [{"role": m.role, "content": m.content} for m in req.history]

    try:
        result = await ask(req.question, chat_history=history)
    except QueueTimeoutError as e:
        # 503 = "server's temporarily overloaded", not a real error — the
        # frontend can show this as "the AI is busy, try again" instead of
        # a generic failure.
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "answer": result["answer"],
        "was_queued": result["was_queued"],
        "queue_position": result["queue_position"],
    }   