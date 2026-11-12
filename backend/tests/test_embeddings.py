import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.config import Settings, get_settings
from app.services import embeddings, llm

DIM = 4


class FakeClient:
    def __init__(self, dim=DIM, shuffle=False, error=None):
        self.calls = []
        self.dim = dim
        self.shuffle = shuffle
        self.error = error
        self.embeddings = SimpleNamespace(create=self._create)

    async def _create(self, model, input):
        if self.error:
            raise self.error
        self.calls.append({"model": model, "input": list(input)})
        # vector encodes the text length so order can be verified
        data = [SimpleNamespace(index=i, embedding=[float(len(t))] + [0.0] * (self.dim - 1)) for i, t in enumerate(input)]
        if self.shuffle:
            data.reverse()
        return SimpleNamespace(data=data)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for n in Settings.model_fields:
        monkeypatch.delenv(n.upper(), raising=False)
    # Settings also reads backend/.env; pin the prefixes so a local .env can't change vector lengths.
    monkeypatch.setenv("EMBEDDING_QUERY_PREFIX", "")
    monkeypatch.setenv("EMBEDDING_DOC_PREFIX", "")
    monkeypatch.setenv("EMBEDDING_DIM", str(DIM))
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "64")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://emb.test/v1")
    get_settings.cache_clear()
    llm.reset_clients()
    yield
    get_settings.cache_clear()
    llm.reset_clients()


def use(monkeypatch, client):
    monkeypatch.setattr(embeddings, "get_embedding_client", lambda: client)
    return client


def test_batches_and_order(monkeypatch):
    fc = use(monkeypatch, FakeClient())
    texts = ["a" * (i + 1) for i in range(150)]
    out = asyncio.run(embeddings.embed_texts(texts))
    assert [len(c["input"]) for c in fc.calls] == [64, 64, 22]
    assert [v[0] for v in out] == [float(i + 1) for i in range(150)]


def test_out_of_order_response_resorted(monkeypatch):
    use(monkeypatch, FakeClient(shuffle=True))
    texts = ["a", "bb", "ccc"]
    out = asyncio.run(embeddings.embed_texts(texts))
    assert [v[0] for v in out] == [1.0, 2.0, 3.0]


def test_wrong_dim_raises(monkeypatch):
    use(monkeypatch, FakeClient(dim=DIM + 1))
    with pytest.raises(embeddings.EmbeddingDimensionError):
        asyncio.run(embeddings.embed_texts(["x"]))


def test_empty_input_no_call(monkeypatch):
    fc = use(monkeypatch, FakeClient())
    assert asyncio.run(embeddings.embed_texts([])) == []
    assert fc.calls == []


def test_prefixes(monkeypatch):
    monkeypatch.setenv("EMBEDDING_QUERY_PREFIX", "Q:")
    monkeypatch.setenv("EMBEDDING_DOC_PREFIX", "D:")
    get_settings.cache_clear()
    fc = use(monkeypatch, FakeClient())
    asyncio.run(embeddings.embed_texts(["x"]))
    asyncio.run(embeddings.embed_texts(["x"], is_query=True))
    assert fc.calls[0]["input"] == ["D:x"]
    assert fc.calls[1]["input"] == ["Q:x"]
    assert fc.calls[0]["model"] == "embeddinggemma"


def test_connection_error_mapped(monkeypatch):
    err = openai.APIConnectionError(request=httpx.Request("POST", "http://emb.test/v1/embeddings"))
    use(monkeypatch, FakeClient(error=err))
    with pytest.raises(llm.ProviderUnavailableError) as ei:
        asyncio.run(embeddings.embed_texts(["x"]))
    assert str(ei.value) == "Cannot reach model provider at http://emb.test/v1"


def test_embed_query(monkeypatch):
    monkeypatch.setenv("EMBEDDING_QUERY_PREFIX", "Q:")
    get_settings.cache_clear()
    fc = use(monkeypatch, FakeClient())
    v = asyncio.run(embeddings.embed_query("abc"))
    assert len(v) == DIM
    assert fc.calls[0]["input"] == ["Q:abc"]


def test_to_pgvector():
    assert embeddings.to_pgvector([1, 0.5, -2.25]) == "[1.0,0.5,-2.25]"
    assert embeddings.to_pgvector([]) == "[]"
