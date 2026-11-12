import uuid
from typing import Any, AsyncIterator

import openai

from app.config import get_settings
from app.services.llm import get_chat_client, provider_unavailable
from app.services.retrieval import SEARCH_TOOL, execute_tool

SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions using the user's uploaded documents. "
    "When a question may be covered by their documents, call the search_documents tool first. "
    "Base answers on the retrieved passages and cite the source filenames. "
    "If nothing relevant is found, say so honestly instead of guessing. "
    "For greetings, chit-chat, or questions about the conversation itself, answer directly without searching."
)


def _accumulate(calls: list[dict], tcs) -> None:
    for tc in tcs:
        idx = getattr(tc, "index", None)
        fn = getattr(tc, "function", None)
        tc_id = getattr(tc, "id", None)
        if isinstance(idx, int) and idx < len(calls) and idx >= 0:
            cur = calls[idx]
        elif isinstance(idx, int) and idx == len(calls):
            cur = None
        elif idx is None and not tc_id and calls:
            cur = calls[-1]
        else:
            cur = None
        if cur is None:
            cur = {"id": "", "name": "", "arguments": ""}
            calls.append(cur)
        if tc_id:
            cur["id"] = tc_id
        if fn is not None:
            if getattr(fn, "name", None):
                cur["name"] += fn.name
            if getattr(fn, "arguments", None):
                cur["arguments"] += fn.arguments


async def run_agent(db, history: list[dict], message: str) -> AsyncIterator[dict[str, Any]]:
    s = get_settings()
    client = get_chat_client()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": message}]
    full_text = ""
    citations: list[dict] = []
    seen: set[tuple] = set()

    for iteration in range(s.max_tool_iterations):
        last = iteration == s.max_tool_iterations - 1
        calls: list[dict] = []
        text = ""
        try:
            stream = await client.chat.completions.create(
                model=s.llm_model,
                messages=messages,
                tools=[SEARCH_TOOL],
                tool_choice="none" if last else "auto",
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    text += delta.content
                    full_text += delta.content
                    yield {"type": "delta", "text": delta.content}
                if getattr(delta, "tool_calls", None):
                    _accumulate(calls, delta.tool_calls)
        except openai.APIConnectionError as e:
            raise provider_unavailable(s.llm_base_url) from e

        calls = [c for c in calls if c["name"]]
        if not calls or last:
            break
        for c in calls:
            c["id"] = c["id"] or f"call_{uuid.uuid4().hex[:24]}"
        messages.append(
            {
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in calls
                ],
            }
        )
        for c in calls:
            yield {"type": "tool", "name": c["name"]}
            result, cites = await execute_tool(db, c["name"], c["arguments"])
            for ct in cites:
                key = (ct["document_id"], ct["chunk_index"])
                if key not in seen:
                    seen.add(key)
                    citations.append(ct)
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})

    yield {"type": "final", "text": full_text, "citations": citations}
