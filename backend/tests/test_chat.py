import json

from app.routers import chat as chat_router
from app.services import openai_responses


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table_name = db, table
        self.op = None
        self.payload = None

    def select(self, *a, **k): self.op = "select"; return self
    def insert(self, p): self.op = "insert"; self.payload = p; return self
    def update(self, p): self.op = "update"; self.payload = p; return self
    def eq(self, *a): return self
    def order(self, *a, **k): return self

    def execute(self):
        class R: pass
        r = R()
        if self.op == "select":
            r.data = self.db.threads if self.table_name == "threads" else []
        else:
            self.db.writes.append((self.table_name, self.op, self.payload))
            r.data = [self.payload]
        return r


class FakeDB:
    def __init__(self, last_id=None):
        self.threads = [{"id": "t1", "title": "New chat", "openai_last_response_id": last_id}]
        self.writes = []

    def table(self, name): return FakeQuery(self, name)


def test_chat_streams_persists_and_chains(client, monkeypatch):
    db = FakeDB(last_id="resp_prev")
    monkeypatch.setattr(chat_router, "user_client", lambda user: db)
    seen = {}

    async def fake_stream(message, prev):
        seen["prev"] = prev
        yield {"type": "delta", "text": "Hel"}
        yield {"type": "delta", "text": "lo"}
        yield {"type": "done", "response_id": "resp_new", "citations": ["doc.pdf"]}

    monkeypatch.setattr(openai_responses, "stream_response", fake_stream)
    r = client.post("/threads/t1/chat", json={"message": "hi"}, headers={"Authorization": "Bearer good"})
    assert r.status_code == 200
    events = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
    assert [e["type"] for e in events] == ["delta", "delta", "done"]
    assert events[-1]["citations"] == ["doc.pdf"]
    assert seen["prev"] == "resp_prev"
    inserts = [w for w in db.writes if w[1] == "insert"]
    assert inserts[0][2]["role"] == "user"
    assert inserts[1][2]["role"] == "assistant" and inserts[1][2]["content"] == "Hello"
    upd = [w for w in db.writes if w[1] == "update"][0][2]
    assert upd["openai_last_response_id"] == "resp_new" and upd["title"] == "hi"


def test_chat_error_event(client, monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(chat_router, "user_client", lambda user: db)

    async def boom(message, prev):
        raise RuntimeError("x")
        yield

    monkeypatch.setattr(openai_responses, "stream_response", boom)
    r = client.post("/threads/t1/chat", json={"message": "hi"}, headers={"Authorization": "Bearer good"})
    assert '"type": "error"' in r.text
    assert db.writes == []  # no orphan user message on failure
