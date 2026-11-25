"""Application settings, read from environment variables or a local .env file.

Secrets are never hard-coded: copy .env.example to .env and fill in the values.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["fake", "anthropic", "openai", "mistral", "google", "ollama"]


class Settings(BaseSettings):
    """Typed runtime configuration for the Invesit backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_env: Literal["dev", "test", "prod"] = "dev"

    database_url: str = Field(
        default="postgresql+psycopg://invesit:invesit@localhost:5432/invesit",
        description="SQLAlchemy URL of the Postgres 16 + pgvector database.",
    )

    test_database_url: str | None = Field(
        default=None,
        description="Throwaway database for integration tests (wiped by tests). "
        "DB tests are skipped when unset or unreachable.",
    )

    # The LLM provider is not chosen yet; "fake" keeps tests offline.
    llm_provider: LLMProvider = "fake"
    llm_model: str = Field(default="", description="Strong model (moderator).")
    llm_model_cheap: str = Field(default="", description="Cheap model (debaters).")
    llm_api_key: SecretStr | None = None

    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None

    @property
    def langfuse_enabled(self) -> bool:
        """Tracing is a no-op unless both Langfuse keys are configured."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
