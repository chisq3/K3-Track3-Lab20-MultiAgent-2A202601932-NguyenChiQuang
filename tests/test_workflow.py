import json

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.critic import CriticAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.schemas import (
    AgentName,
    ResearchQuery,
    RouteName,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient, MockSearchClient
from tests.worker_samples import sample_sources


def _final_answer() -> str:
    return (
        "Shared state supports agent coordination [1].\n\n"
        "## Sources\n"
        "[1] Coordination through shared state — https://example.com/shared-state"
    )


def _workflow(llm: MockLLMClient, search: MockSearchClient) -> MultiAgentWorkflow:
    return MultiAgentWorkflow(
        supervisor=SupervisorAgent(max_iterations=6, timeout_seconds=60),
        researcher=ResearcherAgent(llm, search),
        analyst=AnalystAgent(llm),
        writer=WriterAgent(llm),
        max_iterations=6,
    )


def _critic_workflow(llm: MockLLMClient, search: MockSearchClient) -> MultiAgentWorkflow:
    return MultiAgentWorkflow(
        supervisor=SupervisorAgent(
            max_iterations=8,
            timeout_seconds=60,
            enable_critic=True,
            max_revisions=1,
        ),
        researcher=ResearcherAgent(llm, search),
        analyst=AnalystAgent(llm),
        writer=WriterAgent(llm),
        critic=CriticAgent(llm),
        max_iterations=8,
    )


def _critic_review(decision: str) -> str:
    return json.dumps(
        {
            "decision": decision,
            "quality_score": 9 if decision == "pass" else 6,
            "citation_coverage": 1 if decision == "pass" else 0.6,
            "issues": [] if decision == "pass" else ["The caveat needs clarification."],
            "revision_instructions": None
            if decision == "pass"
            else "Clarify the caveat using source [1].",
        }
    )


def test_workflow_runs_happy_path_to_done() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(content="## Findings\nCoordination uses shared state [1]."),
            LLMResponse(content="## Assessment\nEvidence is medium strength [1]."),
            LLMResponse(content=_final_answer()),
        ]
    )

    result = _workflow(llm, MockSearchClient(sample_sources())).run(
        ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    )

    assert result.status is RunStatus.COMPLETED
    assert result.route_history == [
        RouteName.RESEARCHER,
        RouteName.ANALYST,
        RouteName.WRITER,
        RouteName.DONE,
    ]
    assert result.iteration == 4
    assert result.stop_reason == "completed"
    assert result.usage.search_calls == 1
    assert result.usage.llm_calls == 3
    assert result.agent_attempts == {
        AgentName.RESEARCHER: 1,
        AgentName.ANALYST: 1,
        AgentName.WRITER: 1,
    }
    assert "workflow_total" in result.step_durations_seconds


def test_workflow_retries_analyst_then_recovers() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(content="## Findings\nCoordination uses shared state [1]."),
            LLMResponse(content="Invalid analysis [9]."),
            LLMResponse(content="## Assessment\nEvidence is medium strength [1]."),
            LLMResponse(content=_final_answer()),
        ]
    )

    result = _workflow(llm, MockSearchClient(sample_sources())).run(
        ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    )

    assert result.status is RunStatus.COMPLETED
    assert result.route_history == [
        RouteName.RESEARCHER,
        RouteName.ANALYST,
        RouteName.ANALYST,
        RouteName.WRITER,
        RouteName.DONE,
    ]
    assert result.agent_attempts[AgentName.ANALYST] == 2
    assert result.retry_count == 1
    assert result.fallback_used is False
    assert len(result.errors) == 1


def test_workflow_falls_back_after_two_analyst_failures() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(content="## Findings\nCoordination uses shared state [1]."),
            LLMResponse(content="Invalid analysis [9]."),
            LLMResponse(content="Still invalid [8]."),
            LLMResponse(content=_final_answer()),
        ]
    )

    result = _workflow(llm, MockSearchClient(sample_sources())).run(
        ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    )

    assert result.status is RunStatus.PARTIAL
    assert result.fallback_used is True
    assert result.analysis_notes is None
    assert result.final_answer == _final_answer()
    assert result.usage.llm_calls == 4
    assert result.route_history[-2:] == [RouteName.WRITER, RouteName.DONE]


def test_workflow_stops_after_researcher_terminal_failure() -> None:
    result = _workflow(MockLLMClient([]), MockSearchClient([])).run(
        ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    )

    assert result.status is RunStatus.FAILED
    assert result.stop_reason == "researcher_failed"
    assert result.agent_attempts[AgentName.RESEARCHER] == 2
    assert result.usage.search_calls == 2
    assert result.final_answer is None


def test_workflow_runs_critic_pass_path() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(content="## Findings\nCoordination uses shared state [1]."),
            LLMResponse(content="## Assessment\nEvidence is medium strength [1]."),
            LLMResponse(content=_final_answer()),
            LLMResponse(content=_critic_review("pass")),
        ]
    )

    result = _critic_workflow(llm, MockSearchClient(sample_sources())).run(
        ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    )

    assert result.status is RunStatus.COMPLETED
    assert result.route_history == [
        RouteName.RESEARCHER,
        RouteName.ANALYST,
        RouteName.WRITER,
        RouteName.CRITIC,
        RouteName.DONE,
    ]
    assert result.usage.llm_calls == 4
    assert result.agent_attempts[AgentName.CRITIC] == 1
    assert result.revision_count == 0
    assert result.critic_result is not None
    assert result.critic_result.decision.value == "pass"


def test_workflow_runs_one_revision_and_second_critic_pass() -> None:
    revised_answer = (
        "Shared state coordinates agents with an evidence caveat [1].\n\n"
        "## Sources\n"
        "[1] Coordination through shared state â€” https://example.com/shared-state"
    )
    llm = MockLLMClient(
        [
            LLMResponse(content="## Findings\nCoordination uses shared state [1]."),
            LLMResponse(content="## Assessment\nEvidence is medium strength [1]."),
            LLMResponse(content=_final_answer()),
            LLMResponse(content=_critic_review("revise")),
            LLMResponse(content=revised_answer),
            LLMResponse(content=_critic_review("pass")),
        ]
    )

    result = _critic_workflow(llm, MockSearchClient(sample_sources())).run(
        ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    )

    assert result.status is RunStatus.COMPLETED
    assert result.route_history == [
        RouteName.RESEARCHER,
        RouteName.ANALYST,
        RouteName.WRITER,
        RouteName.CRITIC,
        RouteName.WRITER,
        RouteName.CRITIC,
        RouteName.DONE,
    ]
    assert result.final_answer == revised_answer
    assert result.revision_count == 1
    assert len(result.critic_history) == 2
    assert result.agent_attempts[AgentName.WRITER] == 2
    assert result.agent_attempts[AgentName.CRITIC] == 2
    assert result.usage.llm_calls == 6


def test_workflow_stops_partial_when_second_review_requests_revision() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(content="## Findings\nCoordination uses shared state [1]."),
            LLMResponse(content="## Assessment\nEvidence is medium strength [1]."),
            LLMResponse(content=_final_answer()),
            LLMResponse(content=_critic_review("revise")),
            LLMResponse(content=_final_answer()),
            LLMResponse(content=_critic_review("revise")),
        ]
    )

    result = _critic_workflow(llm, MockSearchClient(sample_sources())).run(
        ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    )

    assert result.status is RunStatus.PARTIAL
    assert result.stop_reason == "critic_revision_limit"
    assert result.route_history[-1] is RouteName.DONE
    assert result.revision_count == 1
    assert len(result.critic_history) == 2
    assert "revision limit" in result.errors[-1]


def test_workflow_preserves_answer_when_critic_fails_twice() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(content="## Findings\nCoordination uses shared state [1]."),
            LLMResponse(content="## Assessment\nEvidence is medium strength [1]."),
            LLMResponse(content=_final_answer()),
            LLMResponse(content="invalid review"),
            LLMResponse(content="still invalid"),
        ]
    )

    result = _critic_workflow(llm, MockSearchClient(sample_sources())).run(
        ResearchState(request=ResearchQuery(query="Explain multi-agent coordination"))
    )

    assert result.status is RunStatus.PARTIAL
    assert result.stop_reason == "critic_failed"
    assert result.final_answer == _final_answer()
    assert result.fallback_used is True
    assert result.agent_attempts[AgentName.CRITIC] == 2
