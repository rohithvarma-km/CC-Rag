import pytest

from app.config import Settings, get_settings
from app.services import llm


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for n in Settings.model_fields:
        monkeypatch.delenv(n.upper(), raising=False)
    get_settings.cache_clear()
    llm.reset_clients()
    yield
    get_settings.cache_clear()
    llm.reset_clients()


def test_chat_client_uses_llm_settings(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://chat.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "chat-key")
    c = llm.get_chat_client()
    assert str(c.base_url).rstrip("/") == "http://chat.test/v1"
    assert c.api_key == "chat-key"
    assert llm.get_chat_client() is c


def test_embedding_client_falls_back_to_llm(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://chat.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "chat-key")
    c = llm.get_embedding_client()
    assert str(c.base_url).rstrip("/") == "http://chat.test/v1"
    assert c.api_key == "chat-key"


def test_embedding_client_override(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://chat.test/v1")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://emb.test/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "emb-key")
    c = llm.get_embedding_client()
    assert str(c.base_url).rstrip("/") == "http://emb.test/v1"
    assert c.api_key == "emb-key"
    assert str(llm.get_chat_client().base_url).rstrip("/") == "http://chat.test/v1"


def test_reset_clients_rebuilds(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://a.test/v1")
    a = llm.get_chat_client()
    llm.reset_clients()
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_BASE_URL", "http://b.test/v1")
    b = llm.get_chat_client()
    assert a is not b
    assert str(b.base_url).rstrip("/") == "http://b.test/v1"


def test_provider_unavailable():
    e = llm.provider_unavailable("http://x/v1")
    assert isinstance(e, llm.ProviderUnavailableError)
    assert str(e) == "Cannot reach model provider at http://x/v1"
