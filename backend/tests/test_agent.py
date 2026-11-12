import asyncio
import copy
from types import SimpleNamespace as NS

import httpx
import openai
import pytest

from app.services import agent
from app.services.llm import ProviderUnavailableError


def text(t):
    return NS(choices=[NS(delta=NS(content=t, tool_calls=None))])


def tc(index=0, id=None, name=None, args=None):
    fn = NS(name=name, arguments=args)
    return NS(choices=[NS(delta=NS(content=None, tool_calls=[NS(index=index, id=id, function=fn)]))])


EMPTY = NS(choices=[])


class FakeClient:
    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []
        self.chat = NS(completions=NS(create=self.create))

    async def create(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        s = self.streams.pop(0)
        if isinstance(s, Exception):
            raise s

        async def gen():
            for c in s:
                yield c

        return gen()


def run(client, monkeypatch, execute=None, history=None, msg="hello"):
    monkeypatch.setattr(agent, "get_chat_client", lambda: client)
    if execute:
        monkeypatch.setattr(agent, "execute_tool", execute)

    async def go():
        return [e async for e in agent.run_agent(object(), history or [], msg)]

    return asyncio.run(go())


def cite(d, i):
    return {"document_id": d, "filename": "f", "chunk_index": i, "snippet": "s", "similarity": 0.5}


def test_plain_answer(monkeypatch):
    c = FakeClient([[EMPTY, text("Hel"), text("lo")]])
    ev = run(c, monkeypatch, history=[{"role": "user", "content": "p"}])
    assert [e["type"] for e in ev] == ["delta", "delta", "final"]
    assert ev[-1] == {"type": "final", "text": "Hello", "citations": []}
    kw = c.calls[0]
    assert kw["stream"] is True and kw["tool_choice"] == "auto" and kw["tools"][0]["function"]["name"] == "search_documents"
    assert [m["role"] for m in kw["messages"]] == ["system", "user", "user"]
    assert "dimensions" not in kw


def test_tool_call_split_args(monkeypatch):
    seen = []

    async def fake_exec(db, name, args):
        seen.append((name, args))
        return "RESULT", [cite("d1", 0)]

    c = FakeClient([
        [text("Let me look. "), tc(0, "call_1", "search_documents", ""), tc(0, None, None, '{"que'),
         tc(0, None, None, 'ry": "cats"}')],
        [text("Answer")],
    ])
    ev = run(c, monkeypatch, fake_exec)
    assert seen == [("search_documents", '{"query": "cats"}')]
    assert [e["type"] for e in ev] == ["delta", "tool", "delta", "final"]
    assert ev[1] == {"type": "tool", "name": "search_documents"}
    assert ev[-1]["text"] == "Let me look. Answer"
    assert ev[-1]["citations"] == [cite("d1", 0)]
    m = c.calls[1]["messages"]
    assert [x["role"] for x in m] == ["system", "user", "assistant", "tool"]
    assert m[2]["tool_calls"][0]["id"] == "call_1"
    assert m[2]["tool_calls"][0]["function"]["arguments"] == '{"query": "cats"}'
    assert m[3] == {"role": "tool", "tool_call_id": "call_1", "content": "RESULT"}


def test_missing_index_tolerated(monkeypatch):
    seen = []

    async def fake_exec(db, name, args):
        seen.append(args)
        return "R", []

    c = FakeClient([
        [tc(None, "id9", "search_documents", '{"query"'), tc(None, None, None, ': "x"}')],
        [text("ok")],
    ])
    ev = run(c, monkeypatch, fake_exec)
    assert seen == ['{"query": "x"}']
    assert c.calls[1]["messages"][-1]["tool_call_id"] == "id9"
    assert ev[-1]["text"] == "ok"


def test_missing_id_generated_and_nameless_dropped(monkeypatch):
    async def fake_exec(db, name, args):
        return "R", []

    c = FakeClient([
        [tc(0, None, "search_documents", "{}"), tc(1, "z", None, "{}")],
        [text("ok")],
    ])
    run(c, monkeypatch, fake_exec)
    calls = c.calls[1]["messages"][-2]["tool_calls"]
    assert len(calls) == 1 and calls[0]["id"]
    assert c.calls[1]["messages"][-1]["tool_call_id"] == calls[0]["id"]


def test_iteration_cap_final_tool_choice_none(monkeypatch):
    n = agent.get_settings().max_tool_iterations

    async def fake_exec(db, name, args):
        return "R", []

    streams = [[tc(0, f"c{i}", "search_documents", '{"query":"q"}')] for i in range(n - 1)]
    streams.append([text("done")])
    c = FakeClient(streams)
    ev = run(c, monkeypatch, fake_exec)
    assert len(c.calls) == n
    assert [k["tool_choice"] for k in c.calls] == ["auto"] * (n - 1) + ["none"]
    assert ev[-1]["text"] == "done"
    assert sum(e["type"] == "final" for e in ev) == 1


def test_invalid_args_recovered(monkeypatch):
    from app.services import retrieval

    async def boom(*a, **k):
        raise AssertionError("no retrieve")

    monkeypatch.setattr(retrieval, "retrieve", boom)
    monkeypatch.setattr(agent, "execute_tool", retrieval.execute_tool)
    c = FakeClient([[tc(0, "c1", "search_documents", "{bad")], [text("sorry")]])
    ev = run(c, monkeypatch)
    tool_msg = c.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["content"].startswith("Error")
    assert ev[-1]["text"] == "sorry"


def test_citations_deduped(monkeypatch):
    results = iter([[cite("d1", 0), cite("d1", 1)], [cite("d1", 1), cite("d2", 0)]])

    async def fake_exec(db, name, args):
        return "R", next(results)

    c = FakeClient([
        [tc(0, "a", "search_documents", '{"query":"1"}')],
        [tc(0, "b", "search_documents", '{"query":"2"}')],
        [text("x")],
    ])
    ev = run(c, monkeypatch, fake_exec)
    assert [(x["document_id"], x["chunk_index"]) for x in ev[-1]["citations"]] == [("d1", 0), ("d1", 1), ("d2", 0)]


def test_connection_error(monkeypatch):
    err = openai.APIConnectionError(request=httpx.Request("POST", "http://x/v1"))
    with pytest.raises(ProviderUnavailableError) as ei:
        run(FakeClient([err]), monkeypatch)
    assert f"Cannot reach model provider at {agent.get_settings().llm_base_url}" == str(ei.value)


def test_other_exception_propagates(monkeypatch):
    with pytest.raises(ValueError):
        run(FakeClient([ValueError("boom")]), monkeypatch)
