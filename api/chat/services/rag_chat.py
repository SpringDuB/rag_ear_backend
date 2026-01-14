from typing import List, Optional

from fastapi import HTTPException
# from fastapi.responses import EventSourceResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from schemas import ChatMessage, ChatRequest


class ChatPayload(ChatRequest):
    kb_ids: Optional[List[str]] = None


async def handle_rag_chat(body: ChatPayload, db: Session):
    # TODO: replace with real RAG pipeline; placeholder to keep contract similar to legacy.
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages is required")

    async def event_gen():
        yield {"event": "message", "data": "RAG streaming placeholder"}

    return EventSourceResponse(event_gen())
