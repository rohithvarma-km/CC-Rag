import asyncio
import json
from types import SimpleNamespace

from app.schemas import SearchDocumentsArgs
from app.services import retrieval


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rows))


def _patch_embed(monkeypatch):
    async def fake(q):
        return [0.5] * 768

    monkeypatch.setattr(retrieval, "embed_query", fake)


ROW = {"chunk_id": "c1", "document_id": "d1", "filename": "a.md", "chunk_index": 2,
       "content": "x" * 300, "similarity": 0.812345}


def test_retrieve_rpc_params(monkeypatch):
    _patch_embed(monkeypatch)
    db = FakeDB([ROW])
    rows = asyncio.run(retrieval.retrieve(db, "hi", 5))
    assert rows == [ROW]
    name, p = db.calls[0]
    assert name == "match_chunks"
    assert set(p) == {"query_embedding", "match_count", "min_similarity"}
    assert isinstance(p["query_embedding"], str)
    assert len(json.loads(p["query_embedding"])) == 768
    assert p["match_count"] == 5


def test_top_k_clamped(monkeypatch):
    _patch_embed(monkeypatch)
    for given, want in [(0, 1), (-3, 1), (99, 10), (7, 7)]:
        db = FakeDB([])
        asyncio.run(retrieval.retrieve(db, "q", given))
        assert db.calls[0][1]["match_count"] == want


def test_retrieve_none_data(monkeypatch):
    _patch_embed(monkeypatch)
    assert asyncio.run(retrieval.retrieve(FakeDB(None), "q", 3)) == []


def test_execute_tool_formats_and_cites(monkeypatch):
    _patch_embed(monkeypatch)
    db = FakeDB([ROW])
    text, cites = asyncio.run(retrieval.execute_tool(db, "search_documents", '{"query": "q"}'))
    assert text.startswith("[1] a.md (chunk 2, similarity 0.8123)\n")
    assert cites == [{"document_id": "d1", "filename": "a.md", "chunk_index": 2,
                      "snippet": "x" * 240, "similarity": 0.8123}]
    assert db.calls[0][1]["match_count"] == 5


def test_execute_tool_empty(monkeypatch):
    _patch_embed(monkeypatch)
    text, cites = asyncio.run(retrieval.execute_tool(FakeDB([]), "search_documents", '{"query": "q"}'))
    assert text.startswith("No relevant passages found")
    assert cites == []


def test_execute_tool_bad_args_no_retrieve(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("retrieve must not be called")

    monkeypatch.setattr(retrieval, "retrieve", boom)
    for bad in ["{not json", "{}", '{"query": ""}', '{"query": "q", "top_k": "x"}', "[1]", ""]:
        text, cites = asyncio.run(retrieval.execute_tool(FakeDB([]), "search_documents", bad))
        assert text.startswith("Error") and cites == []


def test_execute_tool_unknown(monkeypatch):
    text, cites = asyncio.run(retrieval.execute_tool(FakeDB([]), "nope", "{}"))
    assert "unknown tool" in text and cites == []


def test_search_tool_schema():
    f = retrieval.SEARCH_TOOL["function"]
    assert retrieval.SEARCH_TOOL["type"] == "function"
    assert f["name"] == "search_documents"
    assert f["parameters"] == SearchDocumentsArgs.model_json_schema()
