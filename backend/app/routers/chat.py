import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langsmith import traceable

from app.auth import CurrentUser, get_current_user
from app.db import user_client
from app.schemas import ChatRequest
from app.services import openai_responses

router = APIRouter(prefix="/threads", tags=["chat"])
log = logging.getLogger(__name__)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@traceable(name="chat_turn", run_type="chain")
async def run_chat(db, user_id: str, thread_id: str, message: str, thread: dict):
    """Async generator of SSE strings. Metadata (no secrets) attached via the trace."""
    db.table("messages").insert(
        {"thread_id": thread_id, "user_id": user_id, "role": "user", "content": message}
    ).execute()
    title = thread["title"]
    if title == "New chat":
        title = message[:60]

    full = ""
    try:
        async for ev in openai_responses.stream_response(message, thread.get("openai_last_response_id")):
            if ev["type"] == "delta":
                full += ev["text"]
                yield sse(ev)
            else:
                db.table("messages").insert(
                    {
                        "thread_id": thread_id,
                        "user_id": user_id,
                        "role": "assistant",
                        "content": full,
                        "openai_response_id": ev["response_id"],
                    }
                ).execute()
                db.table("threads").update(
                    {
                        "openai_last_response_id": ev["response_id"],
                        "title": title,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", thread_id).execute()
                yield sse({"type": "done", "citations": ev["citations"], "title": title})
    except Exception:
        log.exception("chat stream failed")
        yield sse({"type": "error", "message": "The assistant failed to respond."})


@router.post("/{thread_id}/chat")
async def chat(thread_id: str, body: ChatRequest, user: CurrentUser = Depends(get_current_user)):
    db = user_client(user)
    rows = db.table("threads").select("id,title,openai_last_response_id").eq("id", thread_id).execute().data
    if not rows:
        raise HTTPException(404, "Thread not found")
    gen = run_chat(
        db, user.id, thread_id, body.message, rows[0],
        langsmith_extra={"metadata": {"user_id": user.id, "thread_id": thread_id}},
    )
    return StreamingResponse(gen, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
