"""Supabase Storage over raw httpx, acting as the user (anon apikey + user JWT) so storage RLS applies."""
from urllib.parse import quote

import httpx

from app.config import get_settings

BUCKET = "documents"


class StorageNotFound(Exception):
    pass


def _url(path: str) -> str:
    return f"{get_settings().supabase_url}/storage/v1/object/{BUCKET}/{quote(path, safe='/')}"


def _headers(token: str) -> dict[str, str]:
    return {"apikey": get_settings().supabase_anon_key, "Authorization": f"Bearer {token}"}


async def download(path: str, token: str, *, transport: httpx.AsyncBaseTransport | None = None) -> bytes:
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.get(_url(path), headers=_headers(token))
    if r.status_code in (400, 404):  # Supabase Storage returns 400 or 404 for a missing object
        raise StorageNotFound(path)
    r.raise_for_status()
    return r.content


async def delete(path: str, token: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
    """Delete an object; a missing object is fine."""
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.delete(_url(path), headers=_headers(token))
    if r.status_code == 404:
        return
    r.raise_for_status()
