import pytest

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import AgentName, ResearchQuery, RunStatus
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient
from tests.worker_samples import sample_sources


def _research_state() -> ResearchState:
    return ResearchState(
        request=ResearchQuery(query="Explain multi-agent coordination"),
        sources=sample_sources(),
        research_notes="Shared state supports coordination [1].",
    )


def test_analyst_creates_cited_evidence_assessment() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(
                content="## Claim Assessment\nCoordination claim: High confidence [1].",
                input_tokens=90,
                output_tokens=25,
                cost_usd=0.0001,
            )
        ]
    )
    state = _research_state()

    AnalystAgent(llm).run(state)

    assert state.status is RunStatus.RUNNING
    assert state.analysis_notes is not None and "High confidence" in state.analysis_notes
    assert state.agent_results[0].agent is AgentName.ANALYST
    assert state.usage.llm_calls == 1
    assert "Research notes:" in llm.calls[0].user_prompt
    assert "analyst_total" in state.step_durations_seconds


@pytest.mark.parametrize(
    ("sources_present", "notes", "message"),
    [
        (False, "Notes [1].", "at least one source"),
        (True, None, "research notes"),
    ],
)
def test_analyst_validates_prerequisites(
    sources_present: bool, notes: str | None, message: str
) -> None:
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent coordination"),
        sources=sample_sources() if sources_present else [],
        research_notes=notes,
    )

    with pytest.raises(ValidationError, match=message):
        AnalystAgent(MockLLMClient([])).run(state)

    assert state.status is RunStatus.FAILED
    assert state.usage.llm_calls == 0
