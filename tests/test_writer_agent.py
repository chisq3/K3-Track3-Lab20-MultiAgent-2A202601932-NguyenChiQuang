import pytest

from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import (
    AgentName,
    CriticDecision,
    CriticResult,
    ResearchQuery,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient
from tests.worker_samples import sample_sources


def _writer_state(*, include_analysis: bool = True) -> ResearchState:
    return ResearchState(
        request=ResearchQuery(
            query="Explain multi-agent coordination",
            audience="Python developers",
        ),
        sources=sample_sources(),
        research_notes="Shared state supports coordination [1].",
        analysis_notes="The evidence is direct but limited to one source [1]."
        if include_analysis
        else None,
    )


def _final_answer() -> str:
    return (
        "Shared state lets specialized agents coordinate [1].\n\n"
        "## Sources\n"
        "[1] Coordination through shared state — https://example.com/shared-state"
    )


def test_writer_creates_validated_final_answer() -> None:
    llm = MockLLMClient(
        [LLMResponse(content=_final_answer(), input_tokens=140, output_tokens=40, cost_usd=0.0002)]
    )
    state = _writer_state()

    WriterAgent(llm).run(state)

    assert state.status is RunStatus.RUNNING
    assert state.final_answer == _final_answer()
    assert state.agent_results[0].agent is AgentName.WRITER
    assert state.agent_results[0].metadata["analysis_available"] is True
    assert "Target audience: Python developers" in llm.calls[0].user_prompt
    assert "writer_total" in state.step_durations_seconds


def test_writer_supports_explicit_missing_analysis_fallback() -> None:
    llm = MockLLMClient([LLMResponse(content=_final_answer())])
    state = _writer_state(include_analysis=False)

    WriterAgent(llm).run(state)

    assert state.final_answer is not None
    assert state.agent_results[0].metadata["analysis_available"] is False
    assert "Analysis is unavailable" in llm.calls[0].user_prompt


def test_writer_includes_validation_feedback_on_retry() -> None:
    llm = MockLLMClient([LLMResponse(content=_final_answer())])
    state = _writer_state()
    state.agent_attempts[AgentName.WRITER] = 2
    state.errors.append("Sources section is missing citation labels for source IDs: [1]")

    WriterAgent(llm).run(state)

    assert "Correction required" in llm.calls[0].user_prompt
    assert "missing citation labels" in llm.calls[0].user_prompt


def test_writer_applies_critic_feedback_and_clears_pending_review() -> None:
    llm = MockLLMClient([LLMResponse(content=_final_answer())])
    state = _writer_state()
    state.final_answer = "Previous answer [1]."
    state.revision_count = 1
    state.critic_result = CriticResult(
        decision=CriticDecision.REVISE,
        quality_score=6,
        citation_coverage=0.5,
        issues=["The limitation is missing."],
        citation_issues=["A key claim needs source [1]."],
        unsupported_claims=["Remove the unsupported performance claim."],
        revision_instructions="Add the supported limitation.",
    )

    WriterAgent(llm).run(state)

    assert "Previous answer" in llm.calls[0].user_prompt
    assert "The limitation is missing" in llm.calls[0].user_prompt
    assert "A key claim needs source [1]" in llm.calls[0].user_prompt
    assert "Remove the unsupported performance claim" in llm.calls[0].user_prompt
    assert state.critic_result is None
    assert state.agent_results[0].metadata["is_revision"] is True


def test_writer_rejects_invented_source_url() -> None:
    invalid_answer = (
        "A supported claim [1].\n\n## Sources\n"
        "[1] Fake — https://invented.example/source\n"
        "https://example.com/shared-state"
    )
    state = _writer_state()

    with pytest.raises(ValidationError, match="URL that is not"):
        WriterAgent(MockLLMClient([LLMResponse(content=invalid_answer)])).run(state)

    assert state.status is RunStatus.FAILED
    assert state.final_answer is None


def test_writer_requires_research_evidence() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))

    with pytest.raises(ValidationError, match="at least one source"):
        WriterAgent(MockLLMClient([])).run(state)

    assert state.status is RunStatus.FAILED
