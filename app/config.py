"""
Centralized application settings loaded from environment variables.
Uses pydantic-settings for typed config with automatic .env file support.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # REQUIRED — no default means pydantic-settings raises ValidationError
    # immediately if this key is absent from environment or .env file (per CFG-01)
    OPENAI_API_KEY: str

    # OPTIONAL — sensible default; absolute path resolution happens in database.py
    DATABASE_URL: str = "sqlite:///./data/companies.db"


# Module-level singleton — imported by agent/analyzer.py
settings = Settings()
