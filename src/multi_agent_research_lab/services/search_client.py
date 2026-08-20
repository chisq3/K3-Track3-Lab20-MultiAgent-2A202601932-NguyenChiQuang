"""Tavily search client with validation, deduplication, and explicit retries."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_random_exponential

from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.errors import (
    AgentExecutionError,
    ConfigurationError,
    ValidationError,
)
from multi_agent_research_lab.core.schemas import SourceDocument
from multi_agent_research_lab.observability.tracing import trace_span


class SearchClient:
    """Search Tavily and normalize provider results into domain documents."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._api_key = _required_api_key(self.settings.tavily_api_key)
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=self.settings.provider_timeout_seconds)

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        """Execute one basic Tavily search and return validated, unique sources."""

        clean_query = query.strip()
        if not clean_query:
            raise ValidationError("search query must not be empty")
        if not 1 <= max_results <= 20:
            raise ValidationError("max_results must be between 1 and 20")

        endpoint = f"{self.settings.tavily_base_url.rstrip('/')}/search"
        payload: dict[str, object] = {
            "query": clean_query,
            "search_depth": self.settings.tavily_search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "auto_parameters": False,
            "include_usage": True,
        }

        attempts = 0

        def invoke() -> httpx.Response:
            nonlocal attempts
            attempts += 1
            response = self._client.post(
                endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
            return response

        retryer = Retrying(
            stop=stop_after_attempt(self.settings.provider_max_retries + 1),
            wait=wait_random_exponential(
                multiplier=1,
                min=self.settings.provider_retry_min_seconds,
                max=self.settings.provider_retry_max_seconds,
            ),
            retry=retry_if_exception(_is_retryable_search_error),
            reraise=True,
        )

        with trace_span(
            "tavily-search",
            {
                "query": clean_query,
                "max_results": max_results,
                "search_depth": self.settings.tavily_search_depth,
            },
            run_type="retriever",
        ) as span:
            try:
                response = retryer(invoke)
            except Exception as exc:
                failure_kind = _search_failure_kind(exc)
                raise AgentExecutionError(
                    f"Search request failed ({failure_kind}) after {attempts} attempt(s)"
                ) from exc

            sources = _parse_search_response(response, max_results=max_results)
            span["outputs"] = {
                "attempts": attempts,
                "source_count": len(sources),
                "sources": [{"title": source.title, "url": source.url} for source in sources],
            }
            return sources

    def close(self) -> None:
        """Close HTTP resources owned by this wrapper."""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SearchClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _required_api_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise ConfigurationError("TAVILY_API_KEY is missing or empty")
    return value.strip()


def _is_retryable_search_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in {408, 409, 429} or status >= 500
    return False


def _search_failure_kind(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return "connection"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
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


def _parse_search_response(response: httpx.Response, *, max_results: int) -> list[SourceDocument]:
    try:
        payload: object = response.json()
    except ValueError as exc:
        raise ValidationError("Tavily response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValidationError("Tavily response must be a JSON object")

    results = payload.get("results")
    if not isinstance(results, list):
        raise ValidationError("Tavily response does not contain a results list")

    request_id = payload.get("request_id")
    response_time = payload.get("response_time")
    sources: list[SourceDocument] = []
    seen_urls: set[str] = set()

    for item in results:
        if not isinstance(item, dict):
            continue

        title = _clean_string(item.get("title"))
        snippet = _clean_string(item.get("content"))
        normalized_url = _normalize_source_url(item.get("url"))
        if title is None or snippet is None or normalized_url is None:
            continue
        if normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)
        metadata: dict[str, Any] = {"provider": "tavily"}
        score = item.get("score")
        if isinstance(score, int | float) and not isinstance(score, bool):
            metadata["score"] = float(score)
        if isinstance(request_id, str) and request_id:
            metadata["request_id"] = request_id
        if isinstance(response_time, int | float | str) and not isinstance(response_time, bool):
            metadata["response_time"] = response_time

        sources.append(
            SourceDocument(
                title=title,
                url=normalized_url,
                snippet=snippet,
                metadata=metadata,
            )
        )
        if len(sources) >= max_results:
            break

    return sources


def _clean_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    clean_value = value.strip()
    return clean_value or None


def _normalize_source_url(value: object) -> str | None:
    clean_url = _clean_string(value)
    if clean_url is None:
        return None

    try:
        parsed = urlsplit(clean_url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None

    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))
