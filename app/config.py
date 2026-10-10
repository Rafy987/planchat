from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or the .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PlanChat"
    # Neon Postgres connection string (see .env.example).
    database_url: str | None = None

    # Where uploaded PDFs are saved, and the biggest file we accept.
    upload_dir: Path = Path("uploads")
    max_upload_mb: int = 50

    # Chunking, in characters. ~800 chars is 1-2 paragraphs; 150 chars of overlap
    # is about 1-2 sentences repeated between neighbouring chunks.
    chunk_size: int = 800
    chunk_overlap: int = 150

    # Where the embedding model is downloaded to (~70 MB, git-ignored).
    embedding_cache_dir: Path = Path(".cache/fastembed")

    # How many similar chunks to send to the LLM. 5 x ~800 chars is ~1,000 tokens.
    top_k: int = 5

    # LLM. The main provider is tried first; the other one is the fallback.
    # SecretStr hides keys if settings are ever printed or logged ("**********").
    llm_provider: Literal["groq", "openai"] = "groq"
    groq_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    groq_model: str = "qwen/qwen3.8-27b"
    openai_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 300  # caps answer length (and cost)
    llm_timeout_seconds: float = 30


settings = Settings()
