"""Stateless chat history: we store messages and resend a bounded window on every turn."""
from app.config import get_settings


def trim_history(rows: list[dict], max_messages: int, max_chars: int) -> list[dict]:
    """rows are chronological {role, content}. Cap by count, then drop oldest until under max_chars,
    and make sure the window starts on a user turn."""
    msgs = [{"role": r["role"], "content": r["content"]} for r in rows][-max_messages:] if max_messages > 0 else []
    while msgs and sum(len(m["content"]) for m in msgs) > max_chars:
        msgs.pop(0)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def load_history(db, thread_id: str) -> list[dict]:
    s = get_settings()
    rows = (
        db.table("messages")
        .select("role,content")
        .eq("thread_id", thread_id)
        .order("created_at", desc=True)
        .limit(s.history_max_messages)
        .execute()
        .data
    )
    return trim_history(list(reversed(rows)), s.history_max_messages, s.history_max_chars)
