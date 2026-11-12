import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app


@pytest.fixture
def client(monkeypatch):
    async def fake_verify(token, settings):
        return {"id": "user-1", "email": "a@b.c"} if token == "good" else None

    monkeypatch.setattr(auth, "verify_token", fake_verify)
    return TestClient(app)
