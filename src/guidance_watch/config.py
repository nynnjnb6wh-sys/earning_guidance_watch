"""Runtime configuration loaded from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Secrets never appear in traces or logs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    sec_user_agent: str = Field(
        default="GuidanceWatch/0.1 (research; contact@example.com)",
        alias="SEC_USER_AGENT",
    )
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_model: str | None = Field(default=None, alias="OPENROUTER_MODEL")

    db_path: Path = Field(default=Path("./data/guidance_watch.db"), alias="GUIDANCE_WATCH_DB_PATH")
    cache_dir: Path = Field(default=Path("./data/cache"), alias="GUIDANCE_WATCH_CACHE_DIR")
    reports_dir: Path = Field(default=Path("./reports"), alias="GUIDANCE_WATCH_REPORTS_DIR")

    sec_requests_per_second: float = Field(default=4.0, alias="SEC_REQUESTS_PER_SECOND")


def get_settings() -> Settings:
    """Return fresh settings (cheap; avoids a global mutable singleton)."""
    return Settings()
