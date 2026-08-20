import pytest

from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import AgentName, ResearchQuery, RunStatus
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient, MockSearchClient
from tests.worker_samples import sample_sources


def test_researcher_collects_sources_and_cited_notes() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(
                content="## Key Findings\nShared state supports coordination [1].",
                input_tokens=100,
                output_tokens=20,
                cost_usd=0.0001,
            )
        ]
    )
    search = MockSearchClient(sample_sources())
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent coordination", max_sources=2)
    )

    ResearcherAgent(llm, search).run(state)

    assert state.status is RunStatus.RUNNING
    assert len(state.sources) == 2
    assert state.research_notes is not None and "[1]" in state.research_notes
    assert state.agent_results[0].agent is AgentName.RESEARCHER
    assert state.usage.search_calls == 1
    assert state.usage.llm_calls == 1
    assert search.calls == [("Explain multi-agent coordination", 2)]
    assert "[2] Multi-agent system trade-offs" in llm.calls[0].user_prompt
    assert "researcher_total" in state.step_durations_seconds


def test_researcher_fails_when_search_has_no_sources() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))

    with pytest.raises(ValidationError, match="no valid sources"):
        ResearcherAgent(MockLLMClient([]), MockSearchClient([])).run(state)

    assert state.status is RunStatus.FAILED
    assert state.usage.search_calls == 1
    assert state.usage.llm_calls == 0


def test_researcher_rejects_ungrounded_notes_after_recording_usage() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    llm = MockLLMClient(
        [
            LLMResponse(
                content="A claim with the wrong source [9].", input_tokens=10, output_tokens=8
            )
        ]
    )

    with pytest.raises(ValidationError, match="invalid citation IDs"):
        ResearcherAgent(llm, MockSearchClient(sample_sources())).run(state)

    assert state.status is RunStatus.FAILED
    assert state.usage.llm_calls == 1
    assert state.research_notes is None
