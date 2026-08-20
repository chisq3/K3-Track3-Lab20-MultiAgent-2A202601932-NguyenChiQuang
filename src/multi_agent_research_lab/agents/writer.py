"""Writer worker: synthesize the final cited answer."""

from time import perf_counter

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.agents.evidence import (
    format_numbered_sources,
    validate_grounded_text,
)
from multi_agent_research_lab.agents.protocols import LLMCompletionClient
from multi_agent_research_lab.core.errors import AgentExecutionError, LabError, ValidationError
from multi_agent_research_lab.core.schemas import (
    AgentName,
    AgentResult,
    CriticDecision,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState


class WriterAgent(BaseAgent):
    """Write for the requested audience without adding unsupported evidence."""

    name = AgentName.WRITER

    def __init__(self, llm_client: LLMCompletionClient) -> None:
        self._llm_client = llm_client

    def run(self, state: ResearchState) -> ResearchState:
        started = perf_counter()
        state.status = RunStatus.RUNNING
        state.add_trace_event("writer_started", {"analysis_available": bool(state.analysis_notes)})

        try:
            if not state.sources:
                raise ValidationError("Writer requires at least one source")
            if state.research_notes is None or not state.research_notes.strip():
                raise ValidationError("Writer requires non-empty research notes")

            critic_feedback = state.critic_result
            is_revision = (
                critic_feedback is not None and critic_feedback.decision is CriticDecision.REVISE
            )
            llm_started = perf_counter()
            try:
                response = self._llm_client.complete(
                    _SYSTEM_PROMPT,
                    _build_user_prompt(state),
                    temperature=0.4,
                    max_tokens=1200,
                )
            finally:
                state.record_step_duration("writer_llm", perf_counter() - llm_started)

            state.record_llm_usage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
            )
            citation_ids = validate_grounded_text(
                response.content,
                state.sources,
                require_sources_section=True,
                require_cited_urls=True,
            )
            state.final_answer = response.content
            if is_revision:
                state.critic_result = None
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.WRITER,
                    content=response.content,
                    metadata={
                        "citation_ids": sorted(citation_ids),
                        "analysis_available": bool(state.analysis_notes),
                        "is_revision": is_revision,
                        "revision_count": state.revision_count,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "cost_usd": response.cost_usd,
                    },
                )
            )
            state.add_trace_event(
                "writer_completed",
                {
                    "citation_count": len(citation_ids),
                    "is_revision": is_revision,
                    "revision_count": state.revision_count,
                },
            )
            return state
        except LabError as exc:
            _record_failure(state, exc)
            raise
        except Exception as exc:
            error = AgentExecutionError("Writer agent failed unexpectedly")
            _record_failure(state, error)
            raise error from exc
        finally:
            state.record_step_duration("writer_total", perf_counter() - started)


def _build_user_prompt(state: ResearchState) -> str:
    analysis = state.analysis_notes or (
        "Analysis is unavailable. Use the research notes directly and explicitly state "
        "any resulting limitation."
    )
    correction = ""
    if state.agent_attempts.get(AgentName.WRITER, 0) > 1 and state.errors:
        correction = (
            f"\nCorrection required: the previous draft failed validation with: "
            f"{state.errors[-1]}\nReturn a corrected complete answer.\n"
        )
    critic_revision = ""
    if state.critic_result is not None and state.critic_result.decision is CriticDecision.REVISE:
        findings = [
            *(f"General: {issue}" for issue in state.critic_result.issues),
            *(f"Citation: {issue}" for issue in state.critic_result.citation_issues),
            *(f"Unsupported claim: {issue}" for issue in state.critic_result.unsupported_claims),
        ]
        issues = "\n".join(f"- {finding}" for finding in findings)
        critic_revision = (
            f"\nPrevious answer:\n{state.final_answer}\n\n"
            f"Critic findings:\n{issues}\n\n"
            f"Revision instructions:\n{state.critic_result.revision_instructions}\n"
            "Revise only what the supplied evidence supports. Do not search for or invent new "
            "evidence. Return a complete replacement answer, including its Sources section.\n"
        )
    return (
        f"Research question: {state.request.query}\n"
        f"Target audience: {state.request.audience}\n\n"
        f"Sources:\n{format_numbered_sources(state.sources)}\n\n"
        f"Research notes:\n{state.research_notes}\n\n"
        f"Analysis notes:\n{analysis}\n\n"
        f"{correction}"
        f"{critic_revision}"
        "Write the final answer now."
    )


def _record_failure(state: ResearchState, error: LabError) -> None:
    message = str(error)
    state.status = RunStatus.FAILED
    state.errors.append(message)
    state.add_trace_event("writer_failed", {"error": message})


_SYSTEM_PROMPT = """You are the Writer worker in a multi-agent research system.
Write the final answer for the requested audience from the supplied evidence and analysis.

Rules:
- Use only supplied evidence; cite factual claims inline with the original [n] numbers.
- Do not invent claims, citations, source titles, or URLs.
- Resolve structure and wording yourself, but preserve material caveats and evidence gaps.
- End with a Markdown heading 'Sources' and list only cited sources as [n] title — exact URL.
- Return only the user-facing answer, without mentioning agents, prompts, or internal notes.
"""
