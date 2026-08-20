"""OpenRouter-backed LLM client with explicit retry and usage capture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from openai import APIConnectionError, APIStatusError, OpenAI
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_random_exponential

from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.errors import (
    AgentExecutionError,
    ConfigurationError,
    ValidationError,
)
from multi_agent_research_lab.observability.tracing import trace_span


class _CompletionResource(Protocol):
    def create(self, **kwargs: Any) -> object: ...


class _ChatResource(Protocol):
    completions: _CompletionResource


class LLMProviderClient(Protocol):
    """Small protocol that keeps agents and tests independent from one SDK class."""

    chat: _ChatResource

    def close(self) -> None: ...


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class LLMClient:
    """Call an OpenAI-compatible endpoint through OpenRouter.

    Retry is owned by this class so every agent gets the same behavior. The
    OpenAI SDK's built-in retry is disabled to avoid multiplying attempts.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: LLMProviderClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._owns_client = client is None

        if client is not None:
            self._client = client
            return

        api_key = _required_value(self.settings.openrouter_api_key, "OPENROUTER_API_KEY")
        headers = {"X-Title": self.settings.openrouter_app_name}
        if self.settings.openrouter_site_url and self.settings.openrouter_site_url.strip():
            headers["HTTP-Referer"] = self.settings.openrouter_site_url.strip()

        self._client = cast(
            LLMProviderClient,
            OpenAI(
                api_key=api_key,
                base_url=self.settings.openai_base_url,
                timeout=self.settings.provider_timeout_seconds,
                max_retries=0,
                default_headers=headers,
            ),
        )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Return a validated completion with provider usage metadata."""

        clean_system_prompt = _required_text(system_prompt, "system_prompt")
        clean_user_prompt = _required_text(user_prompt, "user_prompt")
        if not 0 <= temperature <= 2:
            raise ValidationError("temperature must be between 0 and 2")
        if max_tokens is not None and max_tokens < 1:
            raise ValidationError("max_tokens must be greater than zero")

        selected_model = (model or self.settings.openai_model).strip()
        if not selected_model:
            raise ConfigurationError("OPENAI_MODEL is missing or empty")

        request: dict[str, Any] = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": clean_system_prompt},
                {"role": "user", "content": clean_user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        attempts = 0

        def invoke() -> object:
            nonlocal attempts
            attempts += 1
            return self._client.chat.completions.create(**request)

        retryer = Retrying(
            stop=stop_after_attempt(self.settings.provider_max_retries + 1),
            wait=wait_random_exponential(
                multiplier=1,
                min=self.settings.provider_retry_min_seconds,
                max=self.settings.provider_retry_max_seconds,
            ),
            retry=retry_if_exception(_is_retryable_llm_error),
            reraise=True,
        )

        with trace_span(
            "openrouter-chat-completion",
            {
                "model": selected_model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "system_prompt": clean_system_prompt,
                "user_prompt": clean_user_prompt,
            },
            run_type="llm",
        ) as span:
            try:
                response = retryer(invoke)
            except Exception as exc:
                failure_kind = _llm_failure_kind(exc)
                raise AgentExecutionError(
                    f"LLM request failed ({failure_kind}) after {attempts} attempt(s)"
                ) from exc

            result = _parse_completion(response)
            span["outputs"] = {
                "content": result.content,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "attempts": attempts,
            }
            return result

    def close(self) -> None:
        """Close provider resources owned by this wrapper."""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _required_value(value: str | None, variable_name: str) -> str:
    if value is None or not value.strip():
        raise ConfigurationError(f"{variable_name} is missing or empty")
    return value.strip()


def _required_text(value: str, field_name: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise ValidationError(f"{field_name} must not be empty")
    return clean_value


def _is_retryable_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, APIConnectionError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {408, 409, 429} or exc.status_code >= 500
    return False


def _llm_failure_kind(exc: BaseException) -> str:
    if isinstance(exc, APIConnectionError):
        return "connection_or_timeout"
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        if status == 401:
            return "authentication"
        if status == 403:
            return "permission"
        if status == 429:
            return "rate_limit"
        if status >= 500:
            return "provider_server_error"
        return "invalid_request"
    return "unexpected_provider_error"


def _parse_completion(response: object) -> LLMResponse:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        raise ValidationError("LLM response does not contain a completion choice")

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("LLM response content is empty")

    usage = getattr(response, "usage", None)
    input_tokens = _optional_non_negative_int(getattr(usage, "prompt_tokens", None))
    output_tokens = _optional_non_negative_int(getattr(usage, "completion_tokens", None))

    return LLMResponse(
        content=content.strip(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_extract_cost(usage),
    )


def _optional_non_negative_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _extract_cost(usage: object) -> float | None:
    if usage is None:
        return None

    value = getattr(usage, "cost", None)
    if value is None:
        model_extra = getattr(usage, "model_extra", None)
        if isinstance(model_extra, dict):
            value = model_extra.get("cost")

    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value >= 0:
        return float(value)
    return None
