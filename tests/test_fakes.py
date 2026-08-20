import pytest

from multi_agent_research_lab.core.schemas import SourceDocument
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient, MockSearchClient


def test_mock_llm_returns_queued_responses_and_records_calls() -> None:
    client = MockLLMClient([LLMResponse(content="deterministic", input_tokens=3)])

    response = client.complete("system", "user", temperature=0.2, max_tokens=50)

    assert response.content == "deterministic"
    assert client.calls[0].temperature == 0.2
    with pytest.raises(AssertionError, match="no queued response"):
        client.complete("system", "second")


def test_mock_search_returns_a_defensive_copy() -> None:
    source = SourceDocument(title="Source", url="https://example.com", snippet="Evidence")
    client = MockSearchClient([source])

    first = client.search("query", max_results=1)
    second = client.search("query", max_results=1)

    assert first == second == [source]
    assert first[0] is not second[0]
    assert client.calls == [("query", 1), ("query", 1)]
