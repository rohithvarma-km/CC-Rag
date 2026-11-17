import httpx
import pytest

from app.routers import documents
from tests.fakes import FakeDB

H = {"Authorization": "Bearer good"}
H1, H2 = "a" * 64, "b" * 64


def body(name="a.txt", size=10, h=H1):
    return {"filename": name, "size_bytes": size, "content_hash": h}


@pytest.fixture
def db(monkeypatch):
    d = FakeDB(documents=[])
    monkeypatch.setattr(documents, "user_client", lambda user: d)
    return d


def test_requires_auth(client):
    assert client.get("/documents").status_code == 401
    assert client.post("/documents", json=body()).status_code == 401
    assert client.delete("/documents/x").status_code == 401


def test_create_validation(client, db):
    for b in [
        body("a.pdf"),
        body(size=0),
        body(size=10**9),
        body(h="xyz"),  # malformed hash
        body(h="a" * 63),
        {"filename": "a.txt", "size_bytes": 10},  # hash missing
    ]:
        assert client.post("/documents", json=b, headers=H).status_code == 422
    assert db.writes == []


def test_create_ok(client, db):
    r = client.post("/documents", json=body("Notes.MD", h=H1.upper()), headers=H)
    assert r.status_code == 201
    b = r.json()
    assert b["action"] == "created"
    d = b["document"]
    assert d["status"] == "pending" and d["storage_path"] == f"user-1/{d['id']}"
    assert db.tables["documents"][0]["user_id"] == "user-1"
    assert db.tables["documents"][0]["content_hash"] == H1  # normalised to lowercase


def seed(db, **kw):
    row = {"id": "d1", "user_id": "user-1", "filename": "a.txt", "size_bytes": 10, "status": "completed",
           "content_hash": H1, "storage_path": "user-1/d1", "error": None}
    row.update(kw)
    db.tables["documents"] = [row]


def test_unchanged_is_a_noop(client, db):
    seed(db, status="completed")
    r = client.post("/documents", json=body(), headers=H)
    assert r.status_code == 200
    assert r.json()["action"] == "unchanged" and r.json()["document"]["id"] == "d1"
    assert db.writes == [] and len(db.tables["documents"]) == 1


def test_same_hash_in_flight_is_unchanged(client, db):
    seed(db, status="processing")
    r = client.post("/documents", json=body(), headers=H)
    assert r.status_code == 200 and r.json()["action"] == "unchanged"
    assert db.writes == []


def test_same_hash_failed_is_retry(client, db):
    seed(db, status="failed", error="boom")
    r = client.post("/documents", json=body(), headers=H)
    assert r.status_code == 201 and r.json()["action"] == "retry"
    row = db.tables["documents"][0]
    assert row["id"] == "d1" and row["status"] == "pending" and row["error"] is None and row["content_hash"] == H1
    assert len(db.tables["documents"]) == 1


def test_changed_hash_updates_in_place(client, db):
    seed(db, status="completed")
    r = client.post("/documents", json=body(size=99, h=H2), headers=H)
    assert r.status_code == 201 and r.json()["action"] == "updated"
    row = db.tables["documents"][0]
    assert row["id"] == "d1" and row["storage_path"] == "user-1/d1"  # same row, same storage object
    assert row["status"] == "pending" and row["content_hash"] == H2 and row["size_bytes"] == 99
    assert len(db.tables["documents"]) == 1


def test_legacy_row_without_hash_is_updated(client, db):
    seed(db, status="completed", content_hash=None)
    r = client.post("/documents", json=body(), headers=H)
    assert r.json()["action"] == "updated"
    assert db.tables["documents"][0]["content_hash"] == H1


def test_changed_hash_while_processing_conflicts(client, db):
    seed(db, status="processing")
    assert client.post("/documents", json=body(h=H2), headers=H).status_code == 409
    assert db.writes == []


def test_same_filename_other_hash_does_not_create_duplicate_row(client, db):
    assert client.post("/documents", json=body(), headers=H).json()["action"] == "created"
    db.tables["documents"][0]["status"] = "completed"
    assert client.post("/documents", json=body(h=H2), headers=H).json()["action"] == "updated"
    assert len(db.tables["documents"]) == 1


def test_insert_race_resolves_to_the_winner(client, db):
    """A concurrent upload inserts the same filename between our lookup and insert (unique violation)."""

    class Dup(Exception):
        code = "23505"

    existing = {"id": "d1", "user_id": "user-1", "filename": "a.txt", "size_bytes": 10, "status": "completed",
                "content_hash": H1, "storage_path": "user-1/d1", "error": None}
    real_table = db.table
    state = {"selects": 0}

    def table(name):
        q = real_table(name)
        if name != "documents":
            return q
        orig_execute = q.execute

        def execute():
            if q.op == "select":
                state["selects"] += 1
                if state["selects"] == 2:  # the re-lookup after the violation sees the winner
                    db.tables["documents"] = [dict(existing)]
            if q.op == "insert":
                raise Dup("duplicate key value violates unique constraint (23505)")
            return orig_execute()

        q.execute = execute
        return q

    db.table = table
    r = client.post("/documents", json=body(), headers=H)
    assert r.status_code == 200 and r.json()["action"] == "unchanged" and r.json()["document"]["id"] == "d1"


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
