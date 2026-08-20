from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.core.errors import (
    AgentExecutionError,
    ConfigurationError,
    ValidationError,
)
from multi_agent_research_lab.services.search_client import SearchClient


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "TAVILY_API_KEY": "test-tavily-key",
        "PROVIDER_MAX_RETRIES": 2,
        "PROVIDER_RETRY_MIN_SECONDS": 0,
        "PROVIDER_RETRY_MAX_SECONDS": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def valid_payload() -> dict[str, object]:
    return {
        "request_id": "request-1",
        "response_time": "0.25",
        "results": [
            {
                "title": " First source ",
                "url": "https://EXAMPLE.com/article/#section",
                "content": " Evidence one ",
                "score": 0.9,
            },
            {
                "title": "Duplicate",
                "url": "https://example.com/article",
                "content": "Duplicate evidence",
                "score": 0.8,
            },
            {"title": "Missing content", "url": "https://example.com/missing"},
            {
                "title": "Invalid URL",
                "url": "ftp://example.com/file",
                "content": "Not accepted",
            },
            {
                "title": "Second source",
                "url": "https://example.org/two",
                "content": "Evidence two",
                "score": 0.7,
            },
        ],
    }


def test_search_normalizes_filters_and_deduplicates_results() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=valid_payload())

    with make_client(handler) as http_client:
        sources = SearchClient(make_settings(), http_client).search(" graph rag ", 5)

    assert [source.title for source in sources] == ["First source", "Second source"]
    assert sources[0].url == "https://example.com/article"
    assert sources[0].snippet == "Evidence one"
    assert sources[0].metadata == {
        "provider": "tavily",
        "score": 0.9,
        "request_id": "request-1",
        "response_time": "0.25",
    }
    assert captured_request is not None
    assert captured_request.headers["Authorization"] == "Bearer test-tavily-key"
    body = captured_request.read().decode("utf-8")
    assert '"search_depth":"basic"' in body
    assert '"auto_parameters":false' in body


@pytest.mark.parametrize("status_code", [429, 500])
def test_retryable_http_status_is_retried(status_code: int) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(status_code, json={"error": "temporary"})
        return httpx.Response(200, json={"results": []})

    with make_client(handler) as http_client:
        result = SearchClient(make_settings(PROVIDER_MAX_RETRIES=1), http_client).search("query")

    assert result == []
    assert calls == 2


def test_timeout_is_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(200, json={"results": []})

    with make_client(handler) as http_client:
        result = SearchClient(make_settings(PROVIDER_MAX_RETRIES=1), http_client).search("query")

    assert result == []
    assert calls == 2


def test_authentication_error_is_not_retried_or_leaked() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": "invalid key"})

    with make_client(handler) as http_client:
        client = SearchClient(make_settings(), http_client)
        with pytest.raises(AgentExecutionError, match="authentication") as exc_info:
            client.search("query")

    assert calls == 1
    assert "test-tavily-key" not in str(exc_info.value)


def test_invalid_payload_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []})

    with make_client(handler) as http_client:
        client = SearchClient(make_settings(), http_client)
        with pytest.raises(ValidationError, match="results list"):
            client.search("query")


def test_invalid_query_and_limit_are_rejected_before_request() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []})

    with make_client(handler) as http_client:
        client = SearchClient(make_settings(), http_client)
        with pytest.raises(ValidationError, match="query"):
            client.search("   ")
        with pytest.raises(ValidationError, match="max_results"):
            client.search("query", max_results=21)

    assert calls == 0


def test_missing_tavily_key_is_reported() -> None:
    with pytest.raises(ConfigurationError, match="TAVILY_API_KEY"):
        SearchClient(Settings(_env_file=None))
