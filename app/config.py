from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or the .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PlanChat"
    # Neon Postgres connection string. Optional until we add the database (Phase 4).
    database_url: str | None = None


settings = Settings()
