import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langsmith import traceable

from app.auth import CurrentUser, get_current_user
from app.db import user_client
from app.schemas import ChatRequest
from app.services import agent
from app.services.history import load_history
from app.services.llm import ProviderUnavailableError

router = APIRouter(prefix="/threads", tags=["chat"])
log = logging.getLogger(__name__)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@traceable(
    name="chat_turn",
    run_type="chain",
    process_inputs=lambda i: {"message": i.get("message"), "history_messages": len(i.get("history") or [])},
)
async def run_chat(db, user_id: str, thread_id: str, message: str, thread: dict, history: list[dict]):
    """Async generator of SSE strings. Nothing is persisted until the agent returns a non-empty answer."""
    try:
        final = None
        async for ev in agent.run_agent(db, history, message):
            if ev["type"] == "final":
                final = ev
            else:
                yield sse(ev)
        if final is None or not (final.get("text") or "").strip():
            raise RuntimeError("empty assistant response")
        text, citations = final["text"], final.get("citations") or []
        title = thread["title"]
        if title == "New chat":
            title = message[:60]
        db.table("messages").insert(
            {"thread_id": thread_id, "user_id": user_id, "role": "user", "content": message}
        ).execute()
        db.table("messages").insert(
            {
                "thread_id": thread_id,
                "user_id": user_id,
                "role": "assistant",
                "content": text,
                "citations": citations,
            }
        ).execute()
        db.table("threads").update(
            {"title": title, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", thread_id).execute()
        yield sse({"type": "done", "citations": citations, "title": title})
    except ProviderUnavailableError as e:
        yield sse({"type": "error", "message": str(e)})
    except Exception:
        log.exception("chat stream failed")
        yield sse({"type": "error", "message": "The assistant failed to respond."})


@router.post("/{thread_id}/chat")
async def chat(thread_id: str, body: ChatRequest, user: CurrentUser = Depends(get_current_user)):
    db = user_client(user)
    rows = db.table("threads").select("id,title").eq("id", thread_id).execute().data
    if not rows:
        raise HTTPException(404, "Thread not found")
    history = load_history(db, thread_id)  # read before this turn is persisted
    gen = run_chat(
        db, user.id, thread_id, body.message, rows[0], history,
        langsmith_extra={"metadata": {"user_id": user.id, "thread_id": thread_id}},
    )
    return StreamingResponse(gen, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
