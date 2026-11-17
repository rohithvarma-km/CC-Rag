import asyncio
import hashlib
from datetime import datetime, timezone

import pytest

from app.services import ingestion
from tests.fakes import FakeDB

DIM = 768
DOC = {"id": "d1", "user_id": "user-1", "storage_path": "user-1/d1", "status": "processing"}


def make_db(**kw):
    return FakeDB(documents=[dict(DOC)], chunks=kw.pop("chunks", []), **kw)


def patch(monkeypatch, raw=b"hello world. " * 200, embed=None):
    async def dl(path, token, **kw):
        return raw

    async def emb(texts, **k):
        return [[0.1] * DIM for _ in texts]

    monkeypatch.setattr(ingestion.storage, "download", dl)
    monkeypatch.setattr(ingestion, "embed_texts", embed or emb)
    monkeypatch.setattr(ingestion, "to_pgvector", lambda v: "[" + ",".join(map(str, v)) + "]")


def run(db):
    asyncio.run(ingestion.run_ingestion(db, "tok", dict(DOC)))


def test_happy_path(monkeypatch):
    patch(monkeypatch)
    db = make_db()
    run(db)
    d = db.tables["documents"][0]
    assert d["status"] == "completed" and d["chunk_count"] == len(db.tables["chunks"]) > 1
    c = db.tables["chunks"][0]
    assert isinstance(c["embedding"], str) and c["embedding"].count(",") == DIM - 1
    assert c["user_id"] == "user-1" and c["document_id"] == "d1"
    assert [x["chunk_index"] for x in db.tables["chunks"]] == list(range(len(db.tables["chunks"])))


def test_embed_failure_cleans_and_fails(monkeypatch):
    async def boom(texts, **k):
        raise RuntimeError("secret internals")

    patch(monkeypatch, embed=boom)
    db = make_db(chunks=[{"document_id": "d1", "chunk_index": 0}])
    run(db)
    d = db.tables["documents"][0]
    assert d["status"] == "failed" and d["error"] == "Unexpected error (RuntimeError)"
    assert db.tables["chunks"] == []


def test_provider_error_message_shown(monkeypatch):
    async def boom(texts, **k):
        raise ingestion.ProviderUnavailableError("Cannot reach model provider at x")

    patch(monkeypatch, embed=boom)
    db = make_db()
    run(db)
    assert db.tables["documents"][0]["error"] == "Cannot reach model provider at x"


@pytest.mark.parametrize("raw", [b"\xff\xfe\x00bad\x80", b"", b"  \x00\n "])
def test_bad_content_fails(monkeypatch, raw):
    patch(monkeypatch, raw=raw)
    db = make_db()
    run(db)
    d = db.tables["documents"][0]
    assert d["status"] == "failed" and d["error"]
    assert db.tables["chunks"] == []


def test_nul_stripped_and_bom(monkeypatch):
    assert ingestion.decode_text(b"\xef\xbb\xbfa\x00b") == "ab"
    patch(monkeypatch, raw=b"ab\x00cd")
    db = make_db()
    run(db)
    assert db.tables["chunks"][0]["content"] == "abcd"


def test_oversize_fails(monkeypatch):
    patch(monkeypatch, raw=b"x" * 10)
    monkeypatch.setattr(ingestion.get_settings(), "max_upload_bytes", 5)
    db = make_db()
    run(db)
    assert db.tables["documents"][0]["status"] == "failed"


def test_retry_deletes_old_chunks_first(monkeypatch):
    patch(monkeypatch, raw=b"short text")
    db = make_db(chunks=[{"document_id": "d1", "chunk_index": 9, "content": "old"}])
    run(db)
    ops = [(t, o) for t, o, _ in db.writes]
    assert ops.index(("chunks", "delete")) < ops.index(("chunks", "insert"))
    assert [c["content"] for c in db.tables["chunks"]] == ["short text"]


def test_insert_batches_of_100(monkeypatch):
    patch(monkeypatch)
    monkeypatch.setattr(ingestion, "chunk_text", lambda *a: [f"c{i}" for i in range(250)])
    db = make_db()
    run(db)
    inserts = [p for t, o, p in db.writes if (t, o) == ("chunks", "insert")]
    assert [len(p) for p in inserts] == [100, 100, 50]


def test_insert_failure_and_cleanup_failure_swallowed(monkeypatch):
    patch(monkeypatch)
    db = make_db()
    db.fail_on = {("chunks", "insert"): Exception("boom")}
    run(db)  # must not raise
    assert db.tables["documents"][0]["status"] == "failed"

    db2 = make_db()
    db2.fail_on = {("chunks", "insert"): Exception("boom"), ("chunks", "delete"): Exception("FK violation")}
    run(db2)  # delete fails during cleanup, swallowed
    assert db2.tables["documents"][0]["status"] == "failed"


def test_failed_status_update_swallowed(monkeypatch):
    patch(monkeypatch, raw=b"")
    db = make_db()
    db.fail_on = {("documents", "update"): Exception("gone")}
    run(db)


def test_claim_filter_and_none():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert ingestion.claimable_filter(now) == (
        "status.in.(pending,failed),and(status.eq.processing,updated_at.lt.2026-01-01T11:50:00Z)"
    )
    db = FakeDB(documents=[])
    assert ingestion.claim_document(db, "nope") is None
    assert "status.eq.processing,updated_at.lt." in db.or_calls[0][1]
    db2 = make_db()
    row = ingestion.claim_document(db2, "d1")
    assert row["id"] == "d1"
    assert db2.writes[0] == ("documents", "update", {"status": "processing", "error": None})


RAW = b"hello world. " * 200
RAW_HASH = hashlib.sha256(RAW).hexdigest()


def run_doc(db, doc):
    asyncio.run(ingestion.run_ingestion(db, "tok", dict(doc)))


def test_server_hash_is_stored(monkeypatch):
    patch(monkeypatch, raw=RAW)
    db = make_db()
    run_doc(db, {**DOC, "content_hash": RAW_HASH})
    d = db.tables["documents"][0]
    assert d["status"] == "completed" and d["content_hash"] == RAW_HASH


def test_legacy_doc_without_declared_hash_gets_one(monkeypatch):
    patch(monkeypatch, raw=RAW)
    db = make_db()
    run_doc(db, {**DOC, "content_hash": None})
    assert db.tables["documents"][0]["content_hash"] == RAW_HASH


def test_hash_mismatch_fails_with_no_chunks(monkeypatch):
    patch(monkeypatch, raw=RAW)
    db = make_db(chunks=[{"document_id": "d1", "chunk_index": 0, "content": "old"}])
    run_doc(db, {**DOC, "content_hash": "0" * 64})
    d = db.tables["documents"][0]
    assert d["status"] == "failed" and "hash" in d["error"]
    assert db.tables["chunks"] == []
    assert d.get("content_hash") != RAW_HASH


def test_update_replaces_all_old_chunks(monkeypatch):
    patch(monkeypatch, raw=RAW)
    old = [{"document_id": "d1", "chunk_index": i, "content": f"old {i}"} for i in range(50)]
    db = make_db(chunks=old)
    run_doc(db, {**DOC, "content_hash": RAW_HASH})
    chunks = db.tables["chunks"]
    d = db.tables["documents"][0]
    assert d["chunk_count"] == len(chunks) > 0
    assert not any(c["content"].startswith("old") for c in chunks)
    assert sorted(c["chunk_index"] for c in chunks) == list(range(len(chunks)))


def test_failed_update_leaves_no_stale_vectors(monkeypatch):
    async def boom(texts, **k):
        raise ingestion.ProviderUnavailableError("down")

    patch(monkeypatch, raw=RAW, embed=boom)
    db = make_db(chunks=[{"document_id": "d1", "chunk_index": 0, "content": "old"}])
    run_doc(db, {**DOC, "content_hash": RAW_HASH})
    assert db.tables["documents"][0]["status"] == "failed"
    assert db.tables["chunks"] == []


def test_download_is_requested_for_the_declared_version(monkeypatch):
    seen = {}

    async def dl(path, token, **kw):
        seen.update(kw)
        return RAW

    patch(monkeypatch, raw=RAW)
    monkeypatch.setattr(ingestion.storage, "download", dl)
    run_doc(make_db(), {**DOC, "content_hash": RAW_HASH})
    assert seen == {"version": RAW_HASH}
