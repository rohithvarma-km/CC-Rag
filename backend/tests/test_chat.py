import json

import pytest

from app.routers import chat as chat_router
from app.services.llm import ProviderUnavailableError
from tests.fakes import FakeDB

H = {"Authorization": "Bearer good"}


def make_db(**extra):
    return FakeDB(threads=[{"id": "t1", "title": "New chat"}], **extra)


def post(client, msg="hi", tid="t1"):
    r = client.post(f"/threads/{tid}/chat", json={"message": msg}, headers=H)
    events = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
    return r, events


def patch(monkeypatch, db, agent_fn):
    monkeypatch.setattr(chat_router, "user_client", lambda user: db)
    monkeypatch.setattr(chat_router.agent, "run_agent", agent_fn)


def ok_agent(seen=None, citations=("doc.pdf",)):
    async def fake(db, history, message):
        if seen is not None:
            seen["history"], seen["message"] = history, message
            seen["writes_at_start"] = list(db.writes)
        yield {"type": "tool", "name": "search_documents"}
        yield {"type": "delta", "text": "Hel"}
        yield {"type": "delta", "text": "lo"}
        yield {"type": "final", "text": "Hello", "citations": list(citations)}

    return fake


def test_unknown_thread_404(client, monkeypatch):
    patch(monkeypatch, make_db(), ok_agent())
    r = client.post("/threads/nope/chat", json={"message": "hi"}, headers=H)
    assert r.status_code == 404


def test_event_order_and_write_order(client, monkeypatch):
    db = make_db()
    patch(monkeypatch, db, ok_agent())
    r, events = post(client)
    assert r.status_code == 200
    assert [e["type"] for e in events] == ["tool", "delta", "delta", "done"]
    assert events[-1]["citations"] == ["doc.pdf"] and events[-1]["title"] == "hi"
    assert [(w[0], w[1]) for w in db.writes] == [
        ("messages", "insert"), ("messages", "insert"), ("threads", "update")
    ]
    assert db.writes[0][2]["role"] == "user" and db.writes[0][2]["content"] == "hi"
    a = db.writes[1][2]
    assert a["role"] == "assistant" and a["content"] == "Hello" and a["citations"] == ["doc.pdf"]
    upd = db.writes[2][2]
    assert upd["title"] == "hi" and "updated_at" in upd


@pytest.mark.parametrize(
    "exc,msg",
    [
        (RuntimeError("x"), "The assistant failed to respond."),
        (ProviderUnavailableError("provider down"), "provider down"),
    ],
)
def test_error_no_writes(client, monkeypatch, exc, msg):
    db = make_db()

    async def boom(db, history, message):
        yield {"type": "tool", "name": "search_documents"}
        raise exc

    patch(monkeypatch, db, boom)
    r, events = post(client)
    assert events[-1] == {"type": "error", "message": msg}
    assert db.writes == []


@pytest.mark.parametrize("text", ["", "   \n"])
def test_empty_response_errors(client, monkeypatch, text):
    db = make_db()

    async def empty(db, history, message):
        yield {"type": "final", "text": text, "citations": []}

    patch(monkeypatch, db, empty)
    r, events = post(client)
    assert events[-1]["type"] == "error"
    assert db.writes == []


def test_title_only_set_when_new_chat(client, monkeypatch):
    db = FakeDB(threads=[{"id": "t1", "title": "Existing"}])
    patch(monkeypatch, db, ok_agent())
    r, events = post(client, "a long new message")
    assert events[-1]["title"] == "Existing"
    assert [w for w in db.writes if w[1] == "update"][0][2]["title"] == "Existing"


def test_title_truncated_to_60(client, monkeypatch):
    db = make_db()
    patch(monkeypatch, db, ok_agent())
    r, events = post(client, "x" * 100)
    assert events[-1]["title"] == "x" * 60


def test_history_passed_and_read_before_writes(client, monkeypatch):
    db = make_db(messages=[
        {"id": "m1", "thread_id": "t1", "role": "user", "content": "earlier q", "created_at": "2024-01-01T00:00:00"},
        {"id": "m2", "thread_id": "t1", "role": "assistant", "content": "earlier a", "created_at": "2024-01-01T00:00:01"},
    ])
    seen = {}
    patch(monkeypatch, db, ok_agent(seen))
    r, events = post(client, "follow up")
    assert seen["history"] == [
        {"role": "user", "content": "earlier q"},
        {"role": "assistant", "content": "earlier a"},
    ]
    assert seen["message"] == "follow up"
    assert seen["writes_at_start"] == []
    assert events[-1]["type"] == "done"


def test_messages_endpoint_returns_citations(client, monkeypatch):
    from app.routers import threads as threads_router

    db = make_db(messages=[
        {"id": "m1", "thread_id": "t1", "role": "assistant", "content": "a",
         "citations": ["doc.pdf"], "created_at": "2024-01-01T00:00:00"},
    ])
    monkeypatch.setattr(threads_router, "user_client", lambda user: db)
    r = client.get("/threads/t1/messages", headers=H)
    assert r.status_code == 200
    assert r.json()[0]["citations"] == ["doc.pdf"]
