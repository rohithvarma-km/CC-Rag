import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import config
from app.config import Settings, get_settings

ENV_NAMES = [n.upper() for n in Settings.model_fields]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for n in ENV_NAMES:
        monkeypatch.delenv(n, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_embedding_falls_back_to_llm(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm/v1")
    monkeypatch.setenv("LLM_API_KEY", "k1")
    s = Settings(_env_file=None)
    assert s.embedding_base_url == "http://llm/v1"
    assert s.embedding_api_key == "k1"


def test_embedding_overrides(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm/v1")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://emb/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "ek")
    s = Settings(_env_file=None)
    assert s.embedding_base_url == "http://emb/v1"
    assert s.embedding_api_key == "ek"


def test_defaults():
    s = Settings(_env_file=None)
    assert s.embedding_base_url == s.llm_base_url == "http://localhost:11434/v1"
    assert s.chunk_size == 1000 and s.chunk_overlap == 200


def test_int_float_parsing(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIM", "384")
    monkeypatch.setenv("RETRIEVAL_TOP_K", "7")
    monkeypatch.setenv("RETRIEVAL_MIN_SIMILARITY", "0.5")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "123")
    s = Settings(_env_file=None)
    assert s.embedding_dim == 384 and isinstance(s.embedding_dim, int)
    assert s.retrieval_top_k == 7
    assert s.retrieval_min_similarity == 0.5 and isinstance(s.retrieval_min_similarity, float)
    assert s.max_upload_bytes == 123


def test_bad_int_raises(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIM", "abc")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_every_setting_in_env_example():
    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
    present = set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", text, re.M))
    missing = [n for n in ENV_NAMES if n not in present]
    assert not missing, missing


@pytest.mark.parametrize("size", ["0", "-5", str(config.MAX_CHUNK_SIZE + 1)])
def test_chunk_size_bounds(monkeypatch, size):
    monkeypatch.setenv("CHUNK_SIZE", size)
    monkeypatch.setenv("CHUNK_OVERLAP", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_chunk_size_max_ok(monkeypatch):
    monkeypatch.setenv("CHUNK_SIZE", str(config.MAX_CHUNK_SIZE))
    assert Settings(_env_file=None).chunk_size == config.MAX_CHUNK_SIZE


@pytest.mark.parametrize("size,overlap", [("500", "500"), ("500", "600"), ("500", "-1")])
def test_overlap_validation(monkeypatch, size, overlap):
    monkeypatch.setenv("CHUNK_SIZE", size)
    monkeypatch.setenv("CHUNK_OVERLAP", overlap)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_cached(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "m1")
    a = get_settings()
    monkeypatch.setenv("LLM_MODEL", "m2")
    assert get_settings() is a and a.llm_model == "m1"
    get_settings.cache_clear()
    assert get_settings().llm_model == "m2"
