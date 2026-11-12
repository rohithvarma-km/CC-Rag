from typing import Literal

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    title: str = "New chat"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class DocumentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)


class DocumentOut(BaseModel):
    id: str
    filename: str
    status: Literal["pending", "processing", "completed", "failed"]
    error: str | None = None
    chunk_count: int = 0
    size_bytes: int = 0
    storage_path: str
    created_at: str | None = None
    updated_at: str | None = None


class Citation(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    snippet: str
    similarity: float


class SearchDocumentsArgs(BaseModel):
    """Arguments for the search_documents tool."""

    query: str = Field(min_length=1, description="Search query describing the information needed")
    top_k: int = Field(default=5, description="Number of chunks to return (1-10)")


# SSE event shapes (documentation of the wire contract; serialized with json.dumps):
#   {"type": "tool", "name": "search_documents"}
#   {"type": "delta", "text": str}
#   {"type": "done", "citations": [Citation...], "title": str}
#   {"type": "error", "message": str}
