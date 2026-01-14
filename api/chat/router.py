from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import ChatMessage, Message
from .services.agent_chat import AgentPayload, handle_agent_chat
from .services.rag_chat import ChatPayload as RagPayload, handle_rag_chat
from .services.simple_chat import handle_simple_chat

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/stream/rag")
async def chat_rag(body: RagPayload, db: Session = Depends(get_db)):
    return await handle_rag_chat(body, db)


@router.post("/stream/simple")
async def chat_simple(body: ChatMessage, db: Session = Depends(get_db)):
    # Deprecated JSON payload route retained for compatibility; forwards to simple_chat handler.
    return await handle_simple_chat(body.content, [], None, db)


@router.post("/simple_chat")
async def simple_chat(
    prompt: str = Form(..., description="用户输入的文本"),
    model: str | None = Form(None, description="大模型名称"),
    files: list[UploadFile] | None = File(default=None, description="可选上传文件"),
    db: Session = Depends(get_db),
):
    return await handle_simple_chat(prompt, files or [], model, db)


@router.post("/stream/agent")
async def chat_agent(body: AgentPayload, db: Session = Depends(get_db)):
    return await handle_agent_chat(body, db)


@router.get("/health", response_model=Message)
async def chat_health():
    return Message(message="chat ok")
