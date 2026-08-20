"""LangGraph orchestration for the required multi-agent workflow."""

from collections.abc import Hashable
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.agents.critic import CriticAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.errors import AgentExecutionError, LabError
from multi_agent_research_lab.core.schemas import AgentName, RouteName, RunStatus
from multi_agent_research_lab.core.state import ResearchState


class MultiAgentWorkflow:
    """Keep routing in the graph and provider work inside injected agents."""

    def __init__(
        self,
        *,
        supervisor: SupervisorAgent,
        researcher: ResearcherAgent,
        analyst: AnalystAgent,
        writer: WriterAgent,
        max_iterations: int,
        critic: CriticAgent | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._researcher = researcher
        self._analyst = analyst
        self._writer = writer
        self._critic = critic
        self._recursion_limit = max_iterations * 2 + 4

    def build(
        self,
    ) -> CompiledStateGraph[ResearchState, None, ResearchState, ResearchState]:
        """Compile one dynamic Supervisor edge and static worker return edges."""

        builder = StateGraph(ResearchState)
        builder.add_node("supervisor", self._supervisor_node)
        builder.add_node("researcher", self._researcher_node)
        builder.add_node("analyst", self._analyst_node)
        builder.add_node("writer", self._writer_node)
        if self._critic is not None:
            builder.add_node("critic", self._critic_node)

        builder.add_edge(START, "supervisor")
        route_map: dict[Hashable, str] = {
            RouteName.RESEARCHER.value: "researcher",
            RouteName.ANALYST.value: "analyst",
            RouteName.WRITER.value: "writer",
            RouteName.DONE.value: END,
        }
        if self._critic is not None:
            route_map[RouteName.CRITIC.value] = "critic"
        builder.add_conditional_edges(
            "supervisor",
            self._route_next,
            route_map,
        )
        builder.add_edge("researcher", "supervisor")
        builder.add_edge("analyst", "supervisor")
        builder.add_edge("writer", "supervisor")
        if self._critic is not None:
            builder.add_edge("critic", "supervisor")
        return builder.compile(name="multi-agent-research-workflow")

    def run(self, state: ResearchState) -> ResearchState:
        """Invoke the graph with a defensive recursion limit and validated output."""

        from time import perf_counter

        started = perf_counter()
        state.status = RunStatus.RUNNING
        state.add_trace_event("workflow_started", {"recursion_limit": self._recursion_limit})

        try:
            config: RunnableConfig = {
                "recursion_limit": self._recursion_limit,
                "run_name": "multi-agent-langgraph",
            }
            raw_result = self.build().invoke(state, config)
            result = ResearchState.model_validate(raw_result)
        except GraphRecursionError as exc:
            error = AgentExecutionError("Workflow stopped at the LangGraph recursion limit")
            _record_workflow_failure(state, error, perf_counter() - started)
            raise error from exc
        except LabError as exc:
            _record_workflow_failure(state, exc, perf_counter() - started)
            raise
        except Exception as exc:
            error = AgentExecutionError("Multi-agent workflow failed unexpectedly")
            _record_workflow_failure(state, error, perf_counter() - started)
            raise error from exc

        result.record_step_duration("workflow_total", perf_counter() - started)
        result.add_trace_event(
            "workflow_completed",
            {
                "status": result.status.value,
                "stop_reason": result.stop_reason,
                "iterations": result.iteration,
            },
        )
        return result

    def _supervisor_node(self, state: ResearchState) -> dict[str, Any]:
        return self._supervisor.run(state).model_dump(mode="python")

    def _researcher_node(self, state: ResearchState) -> dict[str, Any]:
        return self._run_worker(state, AgentName.RESEARCHER, self._researcher)

    def _analyst_node(self, state: ResearchState) -> dict[str, Any]:
        return self._run_worker(state, AgentName.ANALYST, self._analyst)

    def _writer_node(self, state: ResearchState) -> dict[str, Any]:
        return self._run_worker(state, AgentName.WRITER, self._writer)

    def _critic_node(self, state: ResearchState) -> dict[str, Any]:
        if self._critic is None:
            raise AgentExecutionError("Critic route is enabled without a Critic agent")
        return self._run_worker(state, AgentName.CRITIC, self._critic)

    @staticmethod
    def _run_worker(
        state: ResearchState,
        agent_name: AgentName,
        agent: BaseAgent,
    ) -> dict[str, Any]:
        previous_attempts = state.agent_attempts.get(agent_name, 0)
        state.agent_attempts[agent_name] = previous_attempts + 1
        state.add_trace_event(
            "worker_attempted",
            {"agent": agent_name.value, "attempt": previous_attempts + 1},
        )
        try:
            agent.run(state)
        except LabError:
            state.last_failed_agent = agent_name
        else:
            state.last_failed_agent = None
        return state.model_dump(mode="python")

    @staticmethod
    def _route_next(
        state: ResearchState,
    ) -> Literal["researcher", "analyst", "writer", "critic", "done"]:
        route = state.next_route
        if route is None:
            raise AgentExecutionError("Supervisor did not select a route")
        if route not in {
            RouteName.RESEARCHER,
            RouteName.ANALYST,
            RouteName.WRITER,
            RouteName.CRITIC,
            RouteName.DONE,
        }:
            raise AgentExecutionError(f"Supervisor selected unsupported route: {route.value}")
        return route.value  # type: ignore[return-value]


def _record_workflow_failure(
    state: ResearchState,
    error: LabError,
    elapsed_seconds: float,
) -> None:
    message = str(error)
    state.status = RunStatus.FAILED
    state.next_route = RouteName.DONE
    state.stop_reason = "workflow_error"
    if message not in state.errors:
        state.errors.append(message)
    state.record_step_duration("workflow_total", elapsed_seconds)
    state.add_trace_event("workflow_failed", {"error": message})
