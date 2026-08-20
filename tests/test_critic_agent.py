import json

import pytest

from multi_agent_research_lab.agents.critic import CriticAgent
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import (
    AgentName,
    CriticDecision,
    ResearchQuery,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient
from tests.worker_samples import sample_sources


def _state() -> ResearchState:
    return ResearchState(
        request=ResearchQuery(query="Explain multi-agent coordination"),
        sources=sample_sources(),
        research_notes="Shared state supports coordination [1].",
        analysis_notes="The evidence supports the claim [1].",
        final_answer=(
            "Shared state supports coordination [1].\n\n"
            "## Sources\n"
            "[1] Coordination through shared state â€” https://example.com/shared-state"
        ),
    )


def _review(decision: str = "pass") -> str:
    return json.dumps(
        {
            "decision": decision,
            "quality_score": 8.5 if decision == "pass" else 6.0,
            "citation_coverage": 1.0 if decision == "pass" else 0.6,
            "issues": [] if decision == "pass" else ["A supported caveat is missing."],
            "revision_instructions": None
            if decision == "pass"
            else "Add the caveat from the analysis notes.",
        }
    )


def test_critic_records_structured_pass_decision() -> None:
    llm = MockLLMClient(
        [LLMResponse(content=_review(), input_tokens=100, output_tokens=40, cost_usd=0.0001)]
    )
    state = _state()

    CriticAgent(llm).run(state)

    assert state.status is RunStatus.RUNNING
    assert state.critic_result is not None
    assert state.critic_result.decision is CriticDecision.PASS
    assert state.critic_history == [state.critic_result]
    assert state.agent_results[0].agent is AgentName.CRITIC
    assert state.usage.llm_calls == 1
    assert "critic_total" in state.step_durations_seconds


def test_critic_records_actionable_revision() -> None:
    state = _state()

    CriticAgent(MockLLMClient([LLMResponse(content=_review("revise"))])).run(state)

    assert state.critic_result is not None
    assert state.critic_result.decision is CriticDecision.REVISE
    assert state.critic_result.issues == ["A supported caveat is missing."]
    assert state.critic_result.revision_instructions is not None


def test_critic_rejects_invalid_json_without_removing_answer() -> None:
    state = _state()

    with pytest.raises(ValidationError, match="not a JSON object"):
        CriticAgent(MockLLMClient([LLMResponse(content="PASS")])).run(state)

    assert state.status is RunStatus.FAILED
    assert state.final_answer is not None
    assert state.critic_result is None


def test_critic_revise_requires_actionable_feedback() -> None:
    invalid = json.dumps(
        {
            "decision": "revise",
            "quality_score": 6,
            "citation_coverage": 0.5,
            "issues": [],
            "revision_instructions": None,
        }
    )

    with pytest.raises(ValidationError, match="at least one issue"):
        CriticAgent(MockLLMClient([LLMResponse(content=invalid)])).run(_state())


def test_critic_accepts_categorized_revision_findings() -> None:
    review = json.dumps(
        {
            "decision": "revise",
            "quality_score": 5.5,
            "citation_coverage": 0.5,
            "issues": [],
            "citation_issues": ["The second factual claim has no citation."],
            "unsupported_claims": ["The answer claims a benefit absent from the sources."],
            "revision_instructions": "Remove the unsupported claim and cite the supported one.",
        }
    )
    state = _state()

    CriticAgent(MockLLMClient([LLMResponse(content=review)])).run(state)

    assert state.critic_result is not None
    assert state.critic_result.decision is CriticDecision.REVISE
    assert state.critic_result.issue_count == 2
