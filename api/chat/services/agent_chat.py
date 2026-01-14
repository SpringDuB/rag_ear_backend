from fastapi import HTTPException
# from fastapi.responses import EventSourceResponse
from sse_starlette.sse import EventSourceResponse
from ....schemas import ChatMessage


class AgentPayload(ChatMessage):
    tool: str | None = None


async def handle_agent_chat(body: AgentPayload, _db):
    if not body.content:
        raise HTTPException(status_code=400, detail="prompt required")

    async def event_gen():
        yield {"event": "message", "data": f"Agent placeholder:{body.content}"}

    return EventSourceResponse(event_gen())
