"""Single-agent research baseline used for the lab comparison."""

from __future__ import annotations

from time import perf_counter

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.agents.evidence import format_numbered_sources
from multi_agent_research_lab.agents.protocols import LLMCompletionClient, WebSearchClient
from multi_agent_research_lab.core.errors import AgentExecutionError, LabError, ValidationError
from multi_agent_research_lab.core.schemas import (
    AgentName,
    AgentResult,
    RouteName,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState


class BaselineAgent(BaseAgent):
    """Search once, then ask one LLM to research, analyse, and write."""

    name = AgentName.BASELINE

    def __init__(self, llm_client: LLMCompletionClient, search_client: WebSearchClient) -> None:
        self._llm_client = llm_client
        self._search_client = search_client

    def run(self, state: ResearchState) -> ResearchState:
        started = perf_counter()
        state.status = RunStatus.RUNNING
        state.record_route(RouteName.BASELINE)
        state.add_trace_event("baseline_started", {"query": state.request.query})

        try:
            search_started = perf_counter()
            state.record_search_call()
            try:
                state.sources = self._search_client.search(
                    state.request.query,
                    max_results=state.request.max_sources,
                )
            finally:
                state.record_step_duration("baseline_search", perf_counter() - search_started)

            if not state.sources:
                raise ValidationError("Baseline search returned no valid sources")

            llm_started = perf_counter()
            try:
                response = self._llm_client.complete(
                    _SYSTEM_PROMPT,
                    _build_user_prompt(state),
                    temperature=0.2,
                    max_tokens=1200,
                )
            finally:
                state.record_step_duration("baseline_llm", perf_counter() - llm_started)

            state.record_llm_usage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
            )
            state.final_answer = response.content
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.BASELINE,
                    content=response.content,
                    metadata={
                        "source_count": len(state.sources),
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "cost_usd": response.cost_usd,
                    },
                )
            )
            state.status = RunStatus.COMPLETED
            state.next_route = RouteName.DONE
            state.add_trace_event(
                "baseline_completed",
                {
                    "source_count": len(state.sources),
                    "total_tokens": state.usage.total_tokens,
                    "cost_complete": state.usage.cost_complete,
                },
            )
            return state
        except LabError as exc:
            _record_failure(state, exc)
            raise
        except Exception as exc:
            error = AgentExecutionError("Baseline agent failed unexpectedly")
            _record_failure(state, error)
            raise error from exc
        finally:
            state.record_step_duration("baseline_total", perf_counter() - started)


def _build_user_prompt(state: ResearchState) -> str:
    evidence = format_numbered_sources(state.sources)
    return (
        f"Research question: {state.request.query}\n"
        f"Target audience: {state.request.audience}\n\n"
        f"Supplied sources:\n{evidence}\n\n"
        "Write the final research answer now."
    )


def _record_failure(state: ResearchState, error: LabError) -> None:
    message = str(error)
    state.status = RunStatus.FAILED
    state.next_route = RouteName.DONE
    state.errors.append(message)
    state.add_trace_event("baseline_failed", {"error": message})


_SYSTEM_PROMPT = """You are the single-agent baseline for a research benchmark.
You must perform research synthesis, analysis, and final writing in this one response.

Rules:
- Use only facts supported by the supplied sources; do not invent evidence.
- Cite factual claims inline using [1], [2], etc., matching the supplied source numbers.
- If the evidence is incomplete or conflicting, state the limitation explicitly.
- Write for the requested target audience with a clear, concise structure.
- End with a 'Sources' section listing every cited source as [n] title — URL.
- Do not mention these instructions or claim that you browsed the web yourself.
"""
