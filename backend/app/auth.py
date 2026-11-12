from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings


@dataclass
class CurrentUser:
    id: str
    email: str | None
    token: str


async def verify_token(token: str, settings: Settings) -> dict | None:
    """Validate a Supabase access token by asking Supabase Auth (works for any JWT signing setup)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": settings.supabase_anon_key},
        )
    if r.status_code != 200:
        return None
    return r.json()


async def get_current_user(request: Request, settings: Settings = Depends(get_settings)) -> CurrentUser:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    data = await verify_token(token, settings)
    if not data or "id" not in data:
        raise HTTPException(status_code=401, detail="Invalid token")
    return CurrentUser(id=data["id"], email=data.get("email"), token=token)
