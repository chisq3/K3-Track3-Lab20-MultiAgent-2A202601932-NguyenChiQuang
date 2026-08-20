"""Independent quality and citation evaluation for benchmark outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError as PydanticValidationError

from multi_agent_research_lab.agents.evidence import (
    extract_citation_ids,
    format_numbered_sources,
    validate_grounded_text,
)
from multi_agent_research_lab.agents.protocols import LLMCompletionClient
from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import QualityEvaluation
from multi_agent_research_lab.core.state import ResearchState

_SOURCES_HEADING = re.compile(r"(?im)^#{0,3}\s*sources\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")


@dataclass(frozen=True)
class EvaluationOutcome:
    """Quality score plus judge usage kept outside architecture run cost."""

    evaluation: QualityEvaluation
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None


class QualityJudge:
    """Blind LLM judge applying the same rubric to every architecture."""

    def __init__(self, llm_client: LLMCompletionClient) -> None:
        self._llm_client = llm_client

    def evaluate(self, state: ResearchState) -> EvaluationOutcome:
        if state.final_answer is None or not state.final_answer.strip():
            raise ValidationError("Quality evaluation requires a non-empty final answer")
        if not state.sources:
            raise ValidationError("Quality evaluation requires supplied sources")

        response = self._llm_client.complete(
            _SYSTEM_PROMPT,
            _build_user_prompt(state),
            temperature=0.0,
            max_tokens=500,
        )
        evaluation = _parse_evaluation(response.content)
        return EvaluationOutcome(
            evaluation=evaluation,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
        )


def citation_coverage(text: str) -> float:
    """Return a deterministic sentence-level proxy for main-claim citation coverage.

    The benchmark counts substantive answer sentences before the ``Sources`` section.
    A sentence is covered when it contains at least one ``[n]`` citation. Headings,
    very short fragments, and source-list lines are excluded.
    """

    units = _claim_units(text)
    if not units:
        return 0.0
    cited = sum(bool(extract_citation_ids(unit)) for unit in units)
    return cited / len(units)


def citation_validation_error(state: ResearchState) -> str | None:
    """Return the strict citation-validation error, or ``None`` when valid."""

    if state.final_answer is None or not state.final_answer.strip():
        return "Final answer is empty"
    if not state.sources:
        return "No supplied sources are available"
    try:
        validate_grounded_text(
            state.final_answer,
            state.sources,
            require_sources_section=True,
            require_cited_urls=True,
        )
    except ValidationError as exc:
        return str(exc)
    return None


def citation_validity(state: ResearchState) -> float:
    """Return strict binary citation compliance for the final answer."""

    return 1.0 if citation_validation_error(state) is None else 0.0


def _claim_units(text: str) -> list[str]:
    clean_text = text.strip()
    match = _SOURCES_HEADING.search(clean_text)
    answer_body = clean_text[: match.start()] if match else clean_text

    units: list[str] = []
    for raw_line in answer_body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*+]\s+", "", line)
        for sentence in _SENTENCE_SPLIT.split(line):
            clean_sentence = sentence.strip()
            if len(clean_sentence) < 35:
                continue
            if len(_WORD.findall(clean_sentence)) < 6:
                continue
            units.append(clean_sentence)
    return units


def _parse_evaluation(content: str) -> QualityEvaluation:
    clean_content = content.strip()
    start = clean_content.find("{")
    end = clean_content.rfind("}")
    if start < 0 or end <= start:
        raise ValidationError("Quality judge response is not a JSON object")

    try:
        payload = json.loads(clean_content[start : end + 1])
        return QualityEvaluation.model_validate(payload)
    except (json.JSONDecodeError, PydanticValidationError) as exc:
        raise ValidationError("Quality judge response does not match the rubric schema") from exc


def _build_user_prompt(state: ResearchState) -> str:
    return (
        f"Research question: {state.request.query}\n"
        f"Target audience: {state.request.audience}\n\n"
        f"Supplied evidence:\n{format_numbered_sources(state.sources)}\n\n"
        f"Answer to score:\n{state.final_answer}\n\n"
        "Score this answer with the required rubric."
    )


_SYSTEM_PROMPT = """You are a blind benchmark judge. You do not know which architecture produced
an answer. Evaluate only the research question, supplied evidence, target audience, and answer.
Do not reward verbosity or multi-agent structure by itself. Do not introduce outside facts.

Return exactly one JSON object:
{
  "relevance": number from 0 to 2,
  "completeness": number from 0 to 2,
  "factual_grounding": number from 0 to 2,
  "citation_correctness": number from 0 to 2,
  "clarity": number from 0 to 2,
  "rationale": "brief evidence-based explanation"
}

Rubric:
- Relevance: directly answers the requested research question.
- Completeness: covers the important dimensions supported by the supplied evidence.
- Factual grounding: claims stay within the supplied evidence and preserve caveats.
- Citation correctness: citations are appropriately placed and supported by the evidence.
- Clarity: organization and wording fit the target audience.

Scoring calibration:
- 0 = materially fails the criterion.
- 1 = partially satisfies it or has a meaningful weakness.
- 2 = fully satisfies it with no material weakness.
- Do not award 2 merely because the answer is readable or generally plausible.
- A total of 10/10 is exceptional. Award it only when the answer is complete, precise,
  grounded in the supplied evidence, appropriately cited, and has no meaningful weakness.
- If your rationale identifies a meaningful weakness, the corresponding dimension must
  score below 2.
- Do not reward verbosity, architecture complexity, or facts from your own knowledge.
Return JSON only.
"""
