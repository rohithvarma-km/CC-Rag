from functools import lru_cache

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Export .env to os.environ so the LangSmith SDK (reads LANGSMITH_* from the environment) sees it.
load_dotenv()

# EmbeddingGemma accepts 2048 tokens; stay far below that (chars, worst case ~1 token/char for odd text).
MAX_CHUNK_SIZE = 1500


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_anon_key: str = ""
    cors_origins: str = "http://localhost:5173"

    # Chat model (any OpenAI-compatible Chat Completions endpoint; default: local Ollama).
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "gemma4:e4b"

    # Embeddings (fall back to the LLM_* endpoint/key when empty).
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "embeddinggemma"
    embedding_dim: int = 768
    embedding_query_prefix: str = ""
    embedding_doc_prefix: str = ""
    embedding_batch_size: int = 64

    # Chunking / ingestion
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_upload_bytes: int = 5_000_000

    # Retrieval / agent
    retrieval_top_k: int = 5
    retrieval_min_similarity: float = 0.25
    max_tool_iterations: int = 3

    # Stateless history sent on every turn
    history_max_messages: int = 20
    history_max_chars: int = 24000

    # LANGSMITH_* vars are read directly from the environment by the langsmith SDK.

    @model_validator(mode="after")
    def _defaults_and_bounds(self):
        if not self.embedding_base_url:
            self.embedding_base_url = self.llm_base_url
        if not self.embedding_api_key:
            self.embedding_api_key = self.llm_api_key
        if not 0 < self.chunk_size <= MAX_CHUNK_SIZE:
            raise ValueError(f"CHUNK_SIZE must be between 1 and {MAX_CHUNK_SIZE} (embedding context limit)")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be >= 0 and < CHUNK_SIZE")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
