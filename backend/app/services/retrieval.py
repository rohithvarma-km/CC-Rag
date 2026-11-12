import json
from typing import Any

from langsmith import traceable
from pydantic import ValidationError

from app.config import get_settings
from app.schemas import Citation, SearchDocumentsArgs
from app.services.embeddings import embed_query, to_pgvector

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "Search the user's uploaded documents for passages relevant to a query. "
            "Use this whenever the question may be answered by the user's documents."
        ),
        "parameters": SearchDocumentsArgs.model_json_schema(),
    },
}


@traceable(
    name="retrieve",
    run_type="retriever",
    process_inputs=lambda i: {"query": i.get("query"), "top_k": i.get("top_k")},
)
async def retrieve(db, query: str, top_k: int) -> list[dict[str, Any]]:
    k = max(1, min(10, int(top_k)))
    emb = await embed_query(query)
    resp = db.rpc(
        "match_chunks",
        {
            "query_embedding": to_pgvector(emb),
            "match_count": k,
            "min_similarity": get_settings().retrieval_min_similarity,
        },
    ).execute()
    return resp.data or []


@traceable(
    name="execute_tool",
    run_type="tool",
    process_inputs=lambda i: {"name": i.get("name"), "arguments_json": i.get("arguments_json")},
)
async def execute_tool(db, name: str, arguments_json: str) -> tuple[str, list[dict]]:
    """Run a tool call. Never raises for model mistakes; returns (tool message text, citations)."""
    if name != "search_documents":
        return f"Error: unknown tool '{name}'. Available tool: search_documents.", []
    try:
        args = SearchDocumentsArgs.model_validate(json.loads(arguments_json or "{}"))
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        return (
            "Error: invalid arguments for search_documents "
            f"({type(e).__name__}). Provide JSON like {{\"query\": \"...\", \"top_k\": 5}}.",
            [],
        )
    rows = await retrieve(db, args.query, args.top_k)
    if not rows:
        return "No relevant passages found in the user's documents for this query.", []
    parts: list[str] = []
    citations: list[dict] = []
    for i, r in enumerate(rows, 1):
        sim = round(float(r.get("similarity", 0.0)), 4)
        parts.append(f"[{i}] {r['filename']} (chunk {r['chunk_index']}, similarity {sim})\n{r['content']}")
        citations.append(
            Citation(
                document_id=str(r["document_id"]),
                filename=r["filename"],
                chunk_index=r["chunk_index"],
                snippet=r["content"][:240],
                similarity=sim,
            ).model_dump()
        )
    return "\n\n".join(parts), citations
