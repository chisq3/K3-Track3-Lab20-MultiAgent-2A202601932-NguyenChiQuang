"""Optional Critic worker for grounded quality review and one bounded revision."""

import json
from time import perf_counter

from pydantic import ValidationError as PydanticValidationError

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
    CriticResult,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState


class CriticAgent(BaseAgent):
    """Review answer quality without searching for new evidence."""

    name = AgentName.CRITIC

    def __init__(self, llm_client: LLMCompletionClient) -> None:
        self._llm_client = llm_client

    def run(self, state: ResearchState) -> ResearchState:
        """Validate the answer and return a structured pass/revise decision."""

        started = perf_counter()
        state.status = RunStatus.RUNNING
        state.add_trace_event(
            "critic_started",
            {"revision_count": state.revision_count},
        )

        try:
            if not state.sources:
                raise ValidationError("Critic requires at least one source")
            if state.final_answer is None or not state.final_answer.strip():
                raise ValidationError("Critic requires a non-empty final answer")

            validate_grounded_text(
                state.final_answer,
                state.sources,
                require_sources_section=True,
                require_cited_urls=True,
            )

            llm_started = perf_counter()
            try:
                response = self._llm_client.complete(
                    _SYSTEM_PROMPT,
                    _build_user_prompt(state),
                    temperature=0.0,
                    max_tokens=600,
                )
            finally:
                state.record_step_duration("critic_llm", perf_counter() - llm_started)

            state.record_llm_usage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
            )
            result = _parse_result(response.content)
            state.critic_result = result
            state.critic_history.append(result)
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.CRITIC,
                    content=response.content,
                    metadata={
                        "decision": result.decision.value,
                        "quality_score": result.quality_score,
                        "citation_coverage": result.citation_coverage,
                        "issue_count": result.issue_count,
                        "citation_issue_count": len(result.citation_issues),
                        "unsupported_claim_count": len(result.unsupported_claims),
                        "revision_count": state.revision_count,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "cost_usd": response.cost_usd,
                    },
                )
            )
            state.add_trace_event(
                "critic_completed",
                {
                    "decision": result.decision.value,
                    "quality_score": result.quality_score,
                    "citation_coverage": result.citation_coverage,
                    "issue_count": result.issue_count,
                    "citation_issue_count": len(result.citation_issues),
                    "unsupported_claim_count": len(result.unsupported_claims),
                },
            )
            return state
        except LabError as exc:
            _record_failure(state, exc)
            raise
        except Exception as exc:
            error = AgentExecutionError("Critic agent failed unexpectedly")
            _record_failure(state, error)
            raise error from exc
        finally:
            state.record_step_duration("critic_total", perf_counter() - started)


def _parse_result(content: str) -> CriticResult:
    clean_content = content.strip()
    start = clean_content.find("{")
    end = clean_content.rfind("}")
    if start < 0 or end <= start:
        raise ValidationError("Critic response is not a JSON object")

    try:
        payload = json.loads(clean_content[start : end + 1])
        result = CriticResult.model_validate(payload)
    except (json.JSONDecodeError, PydanticValidationError) as exc:
        raise ValidationError("Critic response does not match the required schema") from exc

    if result.decision is CriticDecision.REVISE:
        if result.issue_count == 0:
            raise ValidationError("Critic revise decision requires at least one issue")
        if result.revision_instructions is None or not result.revision_instructions.strip():
            raise ValidationError("Critic revise decision requires revision instructions")
    return result


def _build_user_prompt(state: ResearchState) -> str:
    return (
        f"Research question: {state.request.query}\n"
        f"Target audience: {state.request.audience}\n\n"
        f"Available sources:\n{format_numbered_sources(state.sources)}\n\n"
        f"Research notes:\n{state.research_notes or 'Unavailable'}\n\n"
        f"Analysis notes:\n{state.analysis_notes or 'Unavailable'}\n\n"
        f"Answer to review:\n{state.final_answer}\n\n"
        "Review the answer and return the required JSON object."
    )


def _record_failure(state: ResearchState, error: LabError) -> None:
    message = str(error)
    state.status = RunStatus.FAILED
    state.errors.append(message)
    state.add_trace_event("critic_failed", {"error": message})


_SYSTEM_PROMPT = """You are the Critic worker in a multi-agent research system.
Evaluate the supplied answer only against the research question and supplied evidence.
Do not browse, introduce new facts, rewrite the answer, or demand citations for transitions.

Return exactly one JSON object with this schema:
{
  "decision": "pass" or "revise",
  "quality_score": number from 0 to 10,
  "citation_coverage": number from 0 to 1,
  "issues": ["general answer-quality issue"],
  "citation_issues": ["missing, invalid, or weakly placed citation issue"],
  "unsupported_claims": ["claim not supported by the supplied evidence"],
  "revision_instructions": "specific bounded instructions" or null
}

Use "pass" only when the answer addresses the question, preserves material caveats, and
its main factual claims are supported by the supplied sources. Use "revise" only for issues
that the Writer can fix using the supplied evidence. A revise decision requires at least one
finding across issues/citation_issues/unsupported_claims and non-empty revision instructions.
Do not request new research. Return JSON only.
"""
