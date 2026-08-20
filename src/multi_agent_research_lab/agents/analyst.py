"""Analyst worker: evaluate claims and evidence quality."""

from time import perf_counter

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.agents.evidence import (
    format_numbered_sources,
    validate_grounded_text,
)
from multi_agent_research_lab.agents.protocols import LLMCompletionClient
from multi_agent_research_lab.core.errors import AgentExecutionError, LabError, ValidationError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult, RunStatus
from multi_agent_research_lab.core.state import ResearchState


class AnalystAgent(BaseAgent):
    """Turn cited research notes into structured evidence-aware analysis."""

    name = AgentName.ANALYST

    def __init__(self, llm_client: LLMCompletionClient) -> None:
        self._llm_client = llm_client

    def run(self, state: ResearchState) -> ResearchState:
        started = perf_counter()
        state.status = RunStatus.RUNNING
        state.add_trace_event("analyst_started", {})

        try:
            if not state.sources:
                raise ValidationError("Analyst requires at least one source")
            if state.research_notes is None or not state.research_notes.strip():
                raise ValidationError("Analyst requires non-empty research notes")

            llm_started = perf_counter()
            try:
                response = self._llm_client.complete(
                    _SYSTEM_PROMPT,
                    _build_user_prompt(state),
                    temperature=0.1,
                    max_tokens=900,
                )
            finally:
                state.record_step_duration("analyst_llm", perf_counter() - llm_started)

            state.record_llm_usage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
            )
            citation_ids = validate_grounded_text(response.content, state.sources)
            state.analysis_notes = response.content
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.ANALYST,
                    content=response.content,
                    metadata={
                        "citation_ids": sorted(citation_ids),
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "cost_usd": response.cost_usd,
                    },
                )
            )
            state.add_trace_event("analyst_completed", {"citation_count": len(citation_ids)})
            return state
        except LabError as exc:
            _record_failure(state, exc)
            raise
        except Exception as exc:
            error = AgentExecutionError("Analyst agent failed unexpectedly")
            _record_failure(state, error)
            raise error from exc
        finally:
            state.record_step_duration("analyst_total", perf_counter() - started)


def _build_user_prompt(state: ResearchState) -> str:
    return (
        f"Research question: {state.request.query}\n\n"
        f"Sources:\n{format_numbered_sources(state.sources)}\n\n"
        f"Research notes:\n{state.research_notes}\n\n"
        "Evaluate the claims and evidence now."
    )


def _record_failure(state: ResearchState, error: LabError) -> None:
    message = str(error)
    state.status = RunStatus.FAILED
    state.errors.append(message)
    state.add_trace_event("analyst_failed", {"error": message})


_SYSTEM_PROMPT = """You are the Analyst worker in a multi-agent research system.
Evaluate the supplied research notes; do not draft the final answer.

Rules:
- Use only supplied sources and preserve their [n] citation numbers.
- Cite every evaluated claim and never invent facts, citations, or URLs.
- Separate evidence from inference and flag unsupported conclusions.
- Return Markdown sections: Claim Assessment, Conflicts, Evidence Gaps, and Suggested Outline.
- For each main claim, rate evidence strength as High, Medium, or Low with a brief reason.
"""
