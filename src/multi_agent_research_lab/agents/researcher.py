"""Researcher worker: collect sources and produce grounded notes."""

from time import perf_counter

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.agents.evidence import (
    format_numbered_sources,
    validate_grounded_text,
)
from multi_agent_research_lab.agents.protocols import LLMCompletionClient, WebSearchClient
from multi_agent_research_lab.core.errors import AgentExecutionError, LabError, ValidationError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult, RunStatus
from multi_agent_research_lab.core.state import ResearchState


class ResearcherAgent(BaseAgent):
    """Search once and turn normalized source snippets into cited research notes."""

    name = AgentName.RESEARCHER

    def __init__(self, llm_client: LLMCompletionClient, search_client: WebSearchClient) -> None:
        self._llm_client = llm_client
        self._search_client = search_client

    def run(self, state: ResearchState) -> ResearchState:
        started = perf_counter()
        state.status = RunStatus.RUNNING
        state.add_trace_event("researcher_started", {"query": state.request.query})

        try:
            search_started = perf_counter()
            state.record_search_call()
            try:
                sources = self._search_client.search(
                    state.request.query,
                    max_results=state.request.max_sources,
                )
            finally:
                state.record_step_duration("researcher_search", perf_counter() - search_started)

            if not sources:
                raise ValidationError("Researcher search returned no valid sources")
            state.sources = sources

            llm_started = perf_counter()
            try:
                response = self._llm_client.complete(
                    _SYSTEM_PROMPT,
                    _build_user_prompt(state),
                    temperature=0.2,
                    max_tokens=900,
                )
            finally:
                state.record_step_duration("researcher_llm", perf_counter() - llm_started)

            state.record_llm_usage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
            )
            citation_ids = validate_grounded_text(response.content, state.sources)
            state.research_notes = response.content
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.RESEARCHER,
                    content=response.content,
                    metadata={
                        "source_count": len(state.sources),
                        "citation_ids": sorted(citation_ids),
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "cost_usd": response.cost_usd,
                    },
                )
            )
            state.add_trace_event(
                "researcher_completed",
                {"source_count": len(state.sources), "citation_count": len(citation_ids)},
            )
            return state
        except LabError as exc:
            _record_failure(state, exc)
            raise
        except Exception as exc:
            error = AgentExecutionError("Researcher agent failed unexpectedly")
            _record_failure(state, error)
            raise error from exc
        finally:
            state.record_step_duration("researcher_total", perf_counter() - started)


def _build_user_prompt(state: ResearchState) -> str:
    return (
        f"Research question: {state.request.query}\n\n"
        f"Supplied sources:\n{format_numbered_sources(state.sources)}\n\n"
        "Produce grounded research notes now."
    )


def _record_failure(state: ResearchState, error: LabError) -> None:
    message = str(error)
    state.status = RunStatus.FAILED
    state.errors.append(message)
    state.add_trace_event("researcher_failed", {"error": message})


_SYSTEM_PROMPT = """You are the Researcher worker in a multi-agent research system.
Your only job is to turn supplied search results into concise, grounded research notes.

Rules:
- Use only the supplied evidence and preserve its [n] citation numbers.
- Cite every factual finding inline; never invent facts, citations, or URLs.
- Do not write the final user-facing answer or perform broad recommendations.
- Return Markdown sections: Key Findings, Evidence by Source, and Evidence Gaps.
- State uncertainty or disagreement between sources explicitly.
"""
