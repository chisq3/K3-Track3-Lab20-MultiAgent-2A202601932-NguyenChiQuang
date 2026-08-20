import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from multi_agent_research_lab.core.config import Settings


def test_settings_defaults(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_CRITIC", raising=False)
    monkeypatch.delenv("MAX_REVISIONS", raising=False)
    monkeypatch.delenv("MAX_ITERATIONS", raising=False)

    settings = Settings(_env_file=None)
    assert settings.openai_model == "openai/gpt-4o-mini"
    assert settings.openai_base_url == "https://openrouter.ai/api/v1"
    assert settings.langsmith_tracing is True
    assert settings.langsmith_endpoint is None
    assert settings.langsmith_workspace_id is None
    assert settings.enable_critic is False
    assert settings.max_revisions == 1
    assert settings.max_iterations >= 1
    assert settings.effective_max_iterations == settings.max_iterations
    assert settings.provider_timeout_seconds == 30
    assert settings.provider_max_retries == 2
    assert settings.tavily_search_depth == "basic"


def test_retry_window_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="PROVIDER_RETRY_MAX_SECONDS"):
        Settings(
            _env_file=None,
            PROVIDER_RETRY_MIN_SECONDS=5,
            PROVIDER_RETRY_MAX_SECONDS=1,
        )


def test_critic_budget_preserves_core_iteration_headroom() -> None:
    settings = Settings(
        _env_file=None,
        ENABLE_CRITIC=True,
        MAX_ITERATIONS=6,
        MAX_REVISIONS=1,
    )

    assert settings.effective_max_iterations == 9
