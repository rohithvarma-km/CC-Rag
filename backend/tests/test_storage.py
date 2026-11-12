import asyncio

import httpx
import pytest

from app.config import Settings, get_settings
from app.services import storage


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for n in Settings.model_fields:
        monkeypatch.delenv(n.upper(), raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def transport(status, body=b"", seen=None):
    def handler(req: httpx.Request):
        if seen is not None:
            seen.append(req)
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handler)


def test_download_url_and_headers():
    seen = []
    out = asyncio.run(storage.download("u1/doc 1.txt", "jwt", transport=transport(200, b"data", seen)))
    assert out == b"data"
    r = seen[0]
    assert r.method == "GET"
    assert str(r.url) == "https://proj.supabase.co/storage/v1/object/documents/u1/doc%201.txt"
    assert r.headers["apikey"] == "anon"
    assert r.headers["authorization"] == "Bearer jwt"


@pytest.mark.parametrize("status", [400, 404])
def test_download_missing(status):
    with pytest.raises(storage.StorageNotFound):
        asyncio.run(storage.download("p", "t", transport=transport(status)))


def test_download_500_raises():
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(storage.download("p", "t", transport=transport(500)))


def test_delete_ok_and_request():
    seen = []
    asyncio.run(storage.delete("u/a.txt", "jwt", transport=transport(200, b"{}", seen)))
    assert seen[0].method == "DELETE"
    assert str(seen[0].url).endswith("/object/documents/u/a.txt")
    assert seen[0].headers["authorization"] == "Bearer jwt"


def test_delete_404_tolerated():
    asyncio.run(storage.delete("p", "t", transport=transport(404)))


def test_delete_500_raises():
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(storage.delete("p", "t", transport=transport(500)))
