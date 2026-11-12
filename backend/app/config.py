from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Export .env to os.environ so the LangSmith SDK (reads LANGSMITH_* from the environment) sees it.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_anon_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_vector_store_id: str = ""
    cors_origins: str = "http://localhost:5173"
    # LANGSMITH_* vars are read directly from the environment by the langsmith SDK.


@lru_cache
def get_settings() -> Settings:
    return Settings()
