import pytest

from multi_agent_research_lab.agents.baseline import BaselineAgent
from multi_agent_research_lab.core.errors import AgentExecutionError, ValidationError
from multi_agent_research_lab.core.schemas import (
    AgentName,
    ResearchQuery,
    RouteName,
    RunStatus,
    SourceDocument,
)
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient, MockSearchClient


def _source() -> SourceDocument:
    return SourceDocument(
        title="Multi-agent systems overview",
        url="https://example.com/multi-agent",
        snippet="Specialized agents can coordinate through shared state.",
    )


def test_baseline_agent_completes_with_sources_and_usage() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(
                content="Agents coordinate through shared state [1].\n\nSources\n[1] overview",
                input_tokens=120,
                output_tokens=30,
                cost_usd=0.00012,
            )
        ]
    )
    search = MockSearchClient([_source()])
    state = ResearchState(
        request=ResearchQuery(
            query="Explain multi-agent systems",
            max_sources=3,
            audience="Python developers",
        )
    )

    result = BaselineAgent(llm, search).run(state)

    assert result is state
    assert state.status is RunStatus.COMPLETED
    assert state.next_route is RouteName.DONE
    assert state.route_history == [RouteName.BASELINE]
    assert state.final_answer is not None and "[1]" in state.final_answer
    assert state.agent_results[0].agent is AgentName.BASELINE
    assert state.usage.llm_calls == 1
    assert state.usage.search_calls == 1
    assert state.usage.total_tokens == 150
    assert state.usage.estimated_cost_usd == pytest.approx(0.00012)
    assert search.calls == [("Explain multi-agent systems", 3)]
    assert "Target audience: Python developers" in llm.calls[0].user_prompt
    assert "https://example.com/multi-agent" in llm.calls[0].user_prompt
    assert "baseline_total" in state.step_durations_seconds


def test_baseline_agent_marks_missing_provider_cost() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    llm = MockLLMClient([LLMResponse(content="Answer [1]", input_tokens=10, output_tokens=5)])

    BaselineAgent(llm, MockSearchClient([_source()])).run(state)

    assert state.status is RunStatus.COMPLETED
    assert state.usage.cost_complete is False
    assert state.usage.estimated_cost_usd == 0


def test_baseline_agent_fails_when_search_returns_no_sources() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))

    with pytest.raises(ValidationError, match="no valid sources"):
        BaselineAgent(MockLLMClient([]), MockSearchClient([])).run(state)

    assert state.status is RunStatus.FAILED
    assert state.next_route is RouteName.DONE
    assert state.usage.search_calls == 1
    assert state.usage.llm_calls == 0
    assert state.errors == ["Baseline search returned no valid sources"]


def test_baseline_agent_preserves_sanitized_provider_failure() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    failure = AgentExecutionError("LLM request failed (rate_limit) after 3 attempt(s)")
    llm = MockLLMClient([failure])

    with pytest.raises(AgentExecutionError, match="rate_limit"):
        BaselineAgent(llm, MockSearchClient([_source()])).run(state)

    assert state.status is RunStatus.FAILED
    assert state.errors == ["LLM request failed (rate_limit) after 3 attempt(s)"]
