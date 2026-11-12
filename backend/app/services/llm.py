"""OpenAI-compatible client factories (chat + embeddings), traced by LangSmith."""
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from app.config import get_settings

_chat: AsyncOpenAI | None = None
_embed: AsyncOpenAI | None = None


class ProviderUnavailableError(RuntimeError):
    """The model provider could not be reached (e.g. Ollama not running)."""


def provider_unavailable(base_url: str) -> ProviderUnavailableError:
    return ProviderUnavailableError(f"Cannot reach model provider at {base_url}")


def get_chat_client() -> AsyncOpenAI:
    global _chat
    if _chat is None:
        s = get_settings()
        _chat = wrap_openai(AsyncOpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key))
    return _chat


def get_embedding_client() -> AsyncOpenAI:
    global _embed
    if _embed is None:
        s = get_settings()
        _embed = wrap_openai(AsyncOpenAI(base_url=s.embedding_base_url, api_key=s.embedding_api_key))
    return _embed


def reset_clients() -> None:
    """For tests."""
    global _chat, _embed
    _chat = _embed = None
