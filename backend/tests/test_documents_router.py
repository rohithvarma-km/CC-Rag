import httpx
import pytest

from app.routers import documents
from tests.fakes import FakeDB

H = {"Authorization": "Bearer good"}


@pytest.fixture
def db(monkeypatch):
    d = FakeDB(documents=[])
    monkeypatch.setattr(documents, "user_client", lambda user: d)
    return d


def test_requires_auth(client):
    assert client.get("/documents").status_code == 401
    assert client.post("/documents", json={"filename": "a.txt", "size_bytes": 1}).status_code == 401
    assert client.delete("/documents/x").status_code == 401


def test_create_validation(client, db):
    for body in [
        {"filename": "a.pdf", "size_bytes": 10},
        {"filename": "a.txt", "size_bytes": 0},
        {"filename": "a.txt", "size_bytes": 10**9},
    ]:
        assert client.post("/documents", json=body, headers=H).status_code == 422
    assert db.writes == []


def test_create_ok(client, db):
    r = client.post("/documents", json={"filename": "Notes.MD", "size_bytes": 10}, headers=H)
    assert r.status_code == 201
    b = r.json()
    assert b["status"] == "pending" and b["storage_path"] == f"user-1/{b['id']}"
    assert db.tables["documents"][0]["user_id"] == "user-1"


def test_list_newest_first(client, db):
    db.tables["documents"] = [
        {"id": "a", "filename": "a.txt", "status": "pending", "storage_path": "p", "created_at": "2026-01-01"},
        {"id": "b", "filename": "b.txt", "status": "pending", "storage_path": "p", "created_at": "2026-02-01"},
    ]
    r = client.get("/documents", headers=H)
    assert [d["id"] for d in r.json()] == ["b", "a"]


def test_ingest_enqueues(client, db, monkeypatch):
    calls = []

    async def fake_run(db_, token, doc):
        calls.append((token, doc["id"]))

    monkeypatch.setattr(documents.ingestion, "claim_document", lambda d, i: {"id": i, "user_id": "user-1"})
    monkeypatch.setattr(documents.ingestion, "run_ingestion", fake_run)
    r = client.post("/documents/d1/ingest", headers=H)
    assert r.status_code == 202 and r.json() == {"id": "d1", "status": "processing"}
    assert calls == [("good", "d1")]


def test_ingest_404_vs_409(client, db, monkeypatch):
    monkeypatch.setattr(documents.ingestion, "claim_document", lambda d, i: None)
    assert client.post("/documents/zzz/ingest", headers=H).status_code == 404
    db.tables["documents"] = [{"id": "d1"}]
    assert client.post("/documents/d1/ingest", headers=H).status_code == 409


def test_delete_order_and_404(client, db, monkeypatch):
    order = []

    async def fake_delete(path, token):
        order.append(("storage", path, token))

    monkeypatch.setattr(documents.storage, "delete", fake_delete)
    assert client.delete("/documents/none", headers=H).status_code == 404
    assert order == []
    db.tables["documents"] = [{"id": "d1", "storage_path": "user-1/d1"}]
    r = client.delete("/documents/d1", headers=H)
    assert r.status_code == 204
    assert order == [("storage", "user-1/d1", "good")]
    assert ("documents", "delete", None) in db.writes and db.tables["documents"] == []


def test_delete_storage_failure_keeps_row(client, db, monkeypatch):
    async def fail(path, token):
        raise httpx.HTTPStatusError("500", request=httpx.Request("DELETE", "http://x"), response=httpx.Response(500))

    monkeypatch.setattr(documents.storage, "delete", fail)
    db.tables["documents"] = [{"id": "d1", "storage_path": "p"}]
    assert client.delete("/documents/d1", headers=H).status_code == 502
    assert len(db.tables["documents"]) == 1
    assert not any(w[1] == "delete" for w in db.writes)
