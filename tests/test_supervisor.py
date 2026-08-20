import pytest

from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.core.schemas import (
    AgentName,
    CriticDecision,
    CriticResult,
    ResearchQuery,
    RouteName,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState
from tests.worker_samples import sample_sources


def _state() -> ResearchState:
    return ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))


@pytest.mark.parametrize(
    ("sources", "research_notes", "analysis_notes", "final_answer", "expected"),
    [
        (False, None, None, None, RouteName.RESEARCHER),
        (True, "Research [1].", None, None, RouteName.ANALYST),
        (True, "Research [1].", "Analysis [1].", None, RouteName.WRITER),
        (True, "Research [1].", "Analysis [1].", "Answer [1].", RouteName.DONE),
    ],
)
def test_supervisor_routes_from_state_artifacts(
    sources: bool,
    research_notes: str | None,
    analysis_notes: str | None,
    final_answer: str | None,
    expected: RouteName,
) -> None:
    state = _state()
    state.sources = sample_sources() if sources else []
    state.research_notes = research_notes
    state.analysis_notes = analysis_notes
    state.final_answer = final_answer

    SupervisorAgent().run(state)

    assert state.next_route is expected
    assert state.route_history == [expected]
    assert state.iteration == 1
    if expected is RouteName.DONE:
        assert state.status is RunStatus.COMPLETED
        assert state.stop_reason == "completed"


def test_supervisor_retries_failed_agent_once() -> None:
    state = _state()
    state.sources = sample_sources()
    state.research_notes = "Research [1]."
    state.last_failed_agent = AgentName.ANALYST
    state.agent_attempts[AgentName.ANALYST] = 1

    SupervisorAgent().run(state)

    assert state.next_route is RouteName.ANALYST
    assert state.retry_count == 1
    assert state.status is RunStatus.RUNNING


def test_supervisor_falls_back_to_writer_after_analyst_attempts() -> None:
    state = _state()
    state.sources = sample_sources()
    state.research_notes = "Research [1]."
    state.last_failed_agent = AgentName.ANALYST
    state.agent_attempts[AgentName.ANALYST] = 2

    SupervisorAgent().run(state)

    assert state.next_route is RouteName.WRITER
    assert state.fallback_used is True
    assert state.last_failed_agent is None


def test_supervisor_stops_at_iteration_guard() -> None:
    state = _state()
    state.iteration = 2

    SupervisorAgent(max_iterations=2).run(state)

    assert state.next_route is RouteName.DONE
    assert state.iteration == 2
    assert state.status is RunStatus.FAILED
    assert state.stop_reason == "max_iterations"


def test_supervisor_stops_after_worker_timeout_budget() -> None:
    state = _state()
    state.step_durations_seconds["researcher_total"] = 61.0

    SupervisorAgent(timeout_seconds=60).run(state)

    assert state.next_route is RouteName.DONE
    assert state.status is RunStatus.FAILED
    assert state.stop_reason == "timeout"


def test_supervisor_routes_completed_draft_to_critic_when_enabled() -> None:
    state = _state()
    state.final_answer = "Answer [1]."

    SupervisorAgent(enable_critic=True).run(state)

    assert state.next_route is RouteName.CRITIC
    assert state.stop_reason is None


def test_supervisor_routes_one_critic_revision_then_stops_on_pass() -> None:
    state = _state()
    state.final_answer = "Answer [1]."
    state.critic_result = CriticResult(
        decision=CriticDecision.REVISE,
        quality_score=6,
        citation_coverage=0.5,
        issues=["Missing caveat."],
        revision_instructions="Add the caveat.",
    )
    supervisor = SupervisorAgent(enable_critic=True, max_revisions=1)

    supervisor.run(state)

    assert state.next_route is RouteName.WRITER
    assert state.revision_count == 1

    state.critic_result = CriticResult(
        decision=CriticDecision.PASS,
        quality_score=9,
        citation_coverage=1,
    )
    supervisor.run(state)

    assert state.next_route is RouteName.DONE
    assert state.status is RunStatus.COMPLETED


def test_supervisor_stops_partial_at_critic_revision_limit() -> None:
    state = _state()
    state.final_answer = "Answer [1]."
    state.revision_count = 1
    state.critic_result = CriticResult(
        decision=CriticDecision.REVISE,
        quality_score=5,
        citation_coverage=0.5,
        issues=["Still incomplete."],
        revision_instructions="Revise again.",
    )

    SupervisorAgent(enable_critic=True, max_revisions=1).run(state)

    assert state.next_route is RouteName.DONE
    assert state.status is RunStatus.PARTIAL
    assert state.stop_reason == "critic_revision_limit"
    assert state.revision_count == 1


def test_supervisor_rejects_more_than_one_revision() -> None:
    with pytest.raises(ValueError, match="0 or 1"):
        SupervisorAgent(enable_critic=True, max_revisions=2)
