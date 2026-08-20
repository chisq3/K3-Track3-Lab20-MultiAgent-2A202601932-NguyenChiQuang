import pytest

from multi_agent_research_lab.core.schemas import (
    AgentName,
    ResearchQuery,
    RouteName,
    RunStatus,
)
from multi_agent_research_lab.runners.workers import run_worker_pipeline
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient, MockSearchClient
from tests.worker_samples import sample_sources


def test_worker_pipeline_handoffs_and_accumulates_metrics() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(
                content="## Key Findings\nCoordination uses shared state [1].",
                input_tokens=100,
                output_tokens=20,
                cost_usd=0.0001,
            ),
            LLMResponse(
                content="## Claim Assessment\nThe evidence is medium strength [1].",
                input_tokens=120,
                output_tokens=30,
                cost_usd=0.0002,
            ),
            LLMResponse(
                content=(
                    "Shared state supports agent coordination [1].\n\n"
                    "## Sources\n"
                    "[1] Coordination through shared state — "
                    "https://example.com/shared-state"
                ),
                input_tokens=160,
                output_tokens=40,
                cost_usd=0.0003,
            ),
        ]
    )

    state = run_worker_pipeline(
        ResearchQuery(query="Explain multi-agent coordination", max_sources=2),
        llm_client=llm,
        search_client=MockSearchClient(sample_sources()),
    )

    assert state.status is RunStatus.COMPLETED
    assert state.next_route is RouteName.DONE
    assert state.route_history == [RouteName.RESEARCHER, RouteName.ANALYST, RouteName.WRITER]
    assert state.iteration == 3
    assert [result.agent for result in state.agent_results] == [
        AgentName.RESEARCHER,
        AgentName.ANALYST,
        AgentName.WRITER,
    ]
    assert state.research_notes is not None
    assert state.analysis_notes is not None
    assert state.final_answer is not None
    assert state.usage.search_calls == 1
    assert state.usage.llm_calls == 3
    assert state.usage.total_tokens == 470
    assert state.usage.estimated_cost_usd == pytest.approx(0.0006)
    assert "worker_pipeline_total" in state.step_durations_seconds
