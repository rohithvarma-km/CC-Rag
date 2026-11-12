"""Module 1 ONLY: OpenAI Responses API with managed threads + file_search.

Module 2 replaces this file (and threads.openai_last_response_id) with stateless
completions, custom ingestion and pgvector retrieval.
"""
from collections.abc import AsyncIterator

from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from app.config import get_settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = wrap_openai(AsyncOpenAI(api_key=get_settings().openai_api_key))
    return _client


async def stream_response(message: str, previous_response_id: str | None) -> AsyncIterator[dict]:
    """Yield {"type":"delta","text":...} then a final {"type":"done","response_id":...,"citations":[...]}."""
    s = get_settings()
    kwargs: dict = {"model": s.openai_model, "input": message, "stream": True}
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id
    if s.openai_vector_store_id:
        kwargs["tools"] = [{"type": "file_search", "vector_store_ids": [s.openai_vector_store_id]}]

    stream = await get_client().responses.create(**kwargs)
    async for event in stream:
        if event.type == "response.output_text.delta":
            yield {"type": "delta", "text": event.delta}
        elif event.type == "response.completed":
            citations: list[str] = []
            for item in event.response.output or []:
                if getattr(item, "type", None) == "message":
                    for part in item.content:
                        for ann in getattr(part, "annotations", None) or []:
                            name = getattr(ann, "filename", None)
                            if name and name not in citations:
                                citations.append(name)
            yield {"type": "done", "response_id": event.response.id, "citations": citations}
        elif event.type in ("response.failed", "error"):
            raise RuntimeError("OpenAI response failed")
