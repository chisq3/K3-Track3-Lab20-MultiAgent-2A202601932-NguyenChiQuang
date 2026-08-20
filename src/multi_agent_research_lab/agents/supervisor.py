"""Deterministic Supervisor for routing and workflow guardrails."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import (
    AgentName,
    CriticDecision,
    RouteName,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState


class SupervisorAgent(BaseAgent):
    """Route from state facts without spending an additional LLM call."""

    name = AgentName.SUPERVISOR

    def __init__(
        self,
        *,
        max_iterations: int = 6,
        timeout_seconds: float = 60.0,
        max_attempts_per_agent: int = 2,
        enable_critic: bool = False,
        max_revisions: int = 1,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts_per_agent < 1:
            raise ValueError("max_attempts_per_agent must be positive")
        if max_revisions not in {0, 1}:
            raise ValueError("max_revisions must be 0 or 1 for the bounded Critic loop")
        self._max_iterations = max_iterations
        self._timeout_seconds = timeout_seconds
        self._max_attempts_per_agent = max_attempts_per_agent
        self._enable_critic = enable_critic
        self._max_revisions = max_revisions

    def run(self, state: ResearchState) -> ResearchState:
        """Select exactly one worker route or stop the workflow."""

        if _worker_elapsed_seconds(state) >= self._timeout_seconds:
            return self._stop(state, "timeout")

        failed_agent = state.last_failed_agent
        if failed_agent is not None:
            attempts = state.agent_attempts.get(failed_agent, 0)
            if attempts < self._max_attempts_per_agent:
                state.retry_count += 1
                state.status = RunStatus.RUNNING
                return self._route(
                    state,
                    RouteName(failed_agent.value),
                    f"retry_{failed_agent.value}",
                )

            if failed_agent is AgentName.ANALYST and state.research_notes and state.sources:
                state.last_failed_agent = None
                state.fallback_used = True
                state.status = RunStatus.PARTIAL
                return self._route(state, RouteName.WRITER, "analyst_fallback")

            if failed_agent is AgentName.CRITIC and state.final_answer:
                state.last_failed_agent = None
                state.fallback_used = True
                return self._stop(state, "critic_failed")

            if failed_agent is AgentName.WRITER and state.revision_count > 0 and state.final_answer:
                state.last_failed_agent = None
                state.fallback_used = True
                return self._stop(state, "writer_revision_failed")

            return self._stop(state, f"{failed_agent.value}_failed")

        if state.final_answer and self._enable_critic:
            critic_result = state.critic_result
            if critic_result is None:
                if state.iteration >= self._max_iterations:
                    return self._stop(state, "max_iterations")
                return self._route(state, RouteName.CRITIC, "critic_review_required")

            if critic_result.decision is CriticDecision.PASS:
                return self._stop(state, "completed")

            if state.revision_count < self._max_revisions:
                if state.iteration >= self._max_iterations:
                    return self._stop(state, "max_iterations")
                state.revision_count += 1
                state.status = RunStatus.RUNNING
                return self._route(state, RouteName.WRITER, "critic_revision_required")

            warning = "Critic requested another revision after the revision limit"
            if warning not in state.errors:
                state.errors.append(warning)
            state.fallback_used = True
            return self._stop(state, "critic_revision_limit")

        if state.final_answer:
            return self._stop(state, "completed")

        if state.iteration >= self._max_iterations:
            return self._stop(state, "max_iterations")

        if not state.sources or not state.research_notes:
            return self._route(state, RouteName.RESEARCHER, "research_required")
        if not state.analysis_notes:
            return self._route(state, RouteName.ANALYST, "analysis_required")
        return self._route(state, RouteName.WRITER, "answer_required")

    def _route(self, state: ResearchState, route: RouteName, reason: str) -> ResearchState:
        state.stop_reason = None
        state.record_route(route)
        state.add_trace_event(
            "supervisor_routed",
            {"route": route.value, "reason": reason, "iteration": state.iteration},
        )
        return state

    def _stop(self, state: ResearchState, reason: str) -> ResearchState:
        state.stop_reason = reason
        if state.iteration < self._max_iterations:
            state.record_route(RouteName.DONE)
        else:
            state.next_route = RouteName.DONE
            if not state.route_history or state.route_history[-1] is not RouteName.DONE:
                state.route_history.append(RouteName.DONE)

        if state.final_answer:
            state.status = RunStatus.PARTIAL if state.fallback_used else RunStatus.COMPLETED
        else:
            state.status = RunStatus.FAILED
        state.add_trace_event(
            "supervisor_stopped",
            {"reason": reason, "status": state.status.value, "iteration": state.iteration},
        )
        return state


def _worker_elapsed_seconds(state: ResearchState) -> float:
    return sum(
        state.step_durations_seconds.get(step, 0.0)
        for step in ("researcher_total", "analyst_total", "writer_total", "critic_total")
    )
