from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APIStatusError

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.core.errors import (
    AgentExecutionError,
    ConfigurationError,
    ValidationError,
)
from multi_agent_research_lab.services.llm_client import LLMClient


class FakeCompletions:
    def __init__(self, outcomes: list[object | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeProviderClient:
    def __init__(self, outcomes: list[object | Exception]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(outcomes))
        self.closed = False

    def close(self) -> None:
        self.closed = True


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "OPENROUTER_API_KEY": "test-openrouter-key",
        "PROVIDER_MAX_RETRIES": 2,
        "PROVIDER_RETRY_MIN_SECONDS": 0,
        "PROVIDER_RETRY_MAX_SECONDS": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def completion_response(content: str = "  answer  ") -> object:
    usage = SimpleNamespace(
        prompt_tokens=11,
        completion_tokens=7,
        model_extra={"cost": 0.00042},
    )
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def connection_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", "https://example.test"))


def status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(status_code, request=request)
    return APIStatusError("provider error", response=response, body=None)


def test_complete_sends_expected_request_and_captures_usage() -> None:
    provider = FakeProviderClient([completion_response()])
    client = LLMClient(make_settings(), provider)

    result = client.complete(
        " system instructions ",
        " user question ",
        temperature=0.3,
        max_tokens=200,
    )

    assert result.content == "answer"
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    assert result.cost_usd == pytest.approx(0.00042)
    request = provider.chat.completions.calls[0]
    assert request["model"] == "openai/gpt-4o-mini"
    assert request["temperature"] == 0.3
    assert request["max_tokens"] == 200
    assert request["messages"] == [
        {"role": "system", "content": "system instructions"},
        {"role": "user", "content": "user question"},
    ]


def test_retryable_connection_error_is_retried() -> None:
    provider = FakeProviderClient([connection_error(), completion_response("recovered")])
    client = LLMClient(make_settings(PROVIDER_MAX_RETRIES=1), provider)

    result = client.complete("system", "user")

    assert result.content == "recovered"
    assert len(provider.chat.completions.calls) == 2


def test_authentication_error_is_not_retried_or_leaked() -> None:
    provider = FakeProviderClient([status_error(401), completion_response()])
    client = LLMClient(make_settings(), provider)

    with pytest.raises(AgentExecutionError, match="authentication") as exc_info:
        client.complete("system", "user")

    assert len(provider.chat.completions.calls) == 1
    assert "test-openrouter-key" not in str(exc_info.value)


def test_empty_completion_is_rejected() -> None:
    provider = FakeProviderClient([completion_response("  ")])
    client = LLMClient(make_settings(), provider)

    with pytest.raises(ValidationError, match="content is empty"):
        client.complete("system", "user")


def test_invalid_request_parameters_are_rejected_before_provider_call() -> None:
    provider = FakeProviderClient([completion_response()])
    client = LLMClient(make_settings(), provider)

    with pytest.raises(ValidationError, match="temperature"):
        client.complete("system", "user", temperature=2.1)
    with pytest.raises(ValidationError, match="max_tokens"):
        client.complete("system", "user", max_tokens=0)

    assert provider.chat.completions.calls == []


def test_missing_key_is_reported_when_constructing_real_client() -> None:
    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        LLMClient(Settings(_env_file=None))
