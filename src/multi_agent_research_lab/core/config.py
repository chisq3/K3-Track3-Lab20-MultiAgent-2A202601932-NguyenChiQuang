"""Application configuration.

Keep config small and explicit. Do not read environment variables directly in agents.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # OpenRouter exposes an OpenAI-compatible API. Keep the provider credential
    # separate so it is never confused with a key issued directly by OpenAI.
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    openai_base_url: str = Field(
        default="https://openrouter.ai/api/v1", validation_alias="OPENAI_BASE_URL"
    )
    openai_model: str = Field(default="openai/gpt-4o-mini", validation_alias="OPENAI_MODEL")
    openrouter_app_name: str = Field(
        default="multi-agent-research-lab", validation_alias="OPENROUTER_APP_NAME"
    )
    openrouter_site_url: str | None = Field(default=None, validation_alias="OPENROUTER_SITE_URL")

    # Retained for backwards compatibility with the original starter config.
    # New OpenRouter integrations should use `openrouter_api_key` above.
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    langsmith_api_key: str | None = Field(default=None, validation_alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(
        default="multi-agent-research-lab", validation_alias="LANGSMITH_PROJECT"
    )
    langsmith_tracing: bool = Field(default=True, validation_alias="LANGSMITH_TRACING")
    langsmith_endpoint: str | None = Field(default=None, validation_alias="LANGSMITH_ENDPOINT")
    langsmith_workspace_id: str | None = Field(
        default=None, validation_alias="LANGSMITH_WORKSPACE_ID"
    )

    langfuse_public_key: str | None = Field(default=None, validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com", validation_alias="LANGFUSE_HOST"
    )

    tavily_api_key: str | None = Field(default=None, validation_alias="TAVILY_API_KEY")
    tavily_base_url: str = Field(
        default="https://api.tavily.com", validation_alias="TAVILY_BASE_URL"
    )
    tavily_search_depth: Literal["basic", "fast", "ultra-fast", "advanced"] = Field(
        default="basic", validation_alias="TAVILY_SEARCH_DEPTH"
    )

    max_iterations: int = Field(default=6, ge=1, le=20, validation_alias="MAX_ITERATIONS")
    timeout_seconds: int = Field(default=60, ge=5, le=600, validation_alias="TIMEOUT_SECONDS")
    provider_timeout_seconds: float = Field(
        default=30.0, gt=0, le=120, validation_alias="PROVIDER_TIMEOUT_SECONDS"
    )
    provider_max_retries: int = Field(
        default=2, ge=0, le=5, validation_alias="PROVIDER_MAX_RETRIES"
    )
    provider_retry_min_seconds: float = Field(
        default=1.0, ge=0, le=30, validation_alias="PROVIDER_RETRY_MIN_SECONDS"
    )
    provider_retry_max_seconds: float = Field(
        default=4.0, ge=0, le=60, validation_alias="PROVIDER_RETRY_MAX_SECONDS"
    )
    enable_critic: bool = Field(default=False, validation_alias="ENABLE_CRITIC")
    max_revisions: int = Field(default=1, ge=0, le=1, validation_alias="MAX_REVISIONS")

    @property
    def effective_max_iterations(self) -> int:
        """Return a guard budget that preserves core retry headroom with Critic enabled.

        ``max_iterations`` remains the core workflow budget. The optional Critic needs
        one review step, and each allowed revision adds one Writer + one Critic step.
        """

        if not self.enable_critic:
            return self.max_iterations
        return self.max_iterations + 1 + (2 * self.max_revisions)

    @model_validator(mode="after")
    def validate_retry_window(self) -> Self:
        if self.provider_retry_max_seconds < self.provider_retry_min_seconds:
            raise ValueError(
                "PROVIDER_RETRY_MAX_SECONDS must be greater than or equal to "
                "PROVIDER_RETRY_MIN_SECONDS"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
