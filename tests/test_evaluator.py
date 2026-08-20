import pytest

from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.evaluator import (
    QualityJudge,
    citation_coverage,
    citation_validation_error,
    citation_validity,
)
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient


def _state(answer: str) -> ResearchState:
    return ResearchState(
        request=ResearchQuery(query="Compare agent architectures"),
        sources=[
            SourceDocument(
                title="Architecture source",
                url="https://example.com/source",
                snippet="Multi-agent systems separate responsibilities across roles.",
            )
        ],
        final_answer=answer,
    )


def test_quality_judge_uses_blind_zero_temperature_rubric() -> None:
    response = LLMResponse(
        content=(
            '{"relevance": 2, "completeness": 1.5, "factual_grounding": 2, '
            '"citation_correctness": 2, "clarity": 1.5, "rationale": "Grounded."}'
        ),
        input_tokens=80,
        output_tokens=30,
        cost_usd=0.0001,
    )
    llm = MockLLMClient([response])
    state = _state(
        "Multi-agent systems can separate responsibilities across roles [1].\n\n"
        "### Sources\n[1] Architecture source — https://example.com/source"
    )

    outcome = QualityJudge(llm).evaluate(state)

    assert outcome.evaluation.total_score == 9.0
    assert outcome.input_tokens == 80
    assert outcome.output_tokens == 30
    assert outcome.cost_usd == pytest.approx(0.0001)
    assert llm.calls[0].temperature == 0.0
    assert "blind benchmark judge" in llm.calls[0].system_prompt
    assert "10/10 is exceptional" in llm.calls[0].system_prompt


def test_quality_judge_rejects_invalid_schema() -> None:
    llm = MockLLMClient([LLMResponse(content='{"relevance": 9}')])
    state = _state(
        "Multi-agent systems can separate responsibilities across roles [1].\n\n"
        "### Sources\n[1] Architecture source — https://example.com/source"
    )

    with pytest.raises(ValidationError, match="rubric schema"):
        QualityJudge(llm).evaluate(state)


def test_citation_coverage_counts_substantive_sentences() -> None:
    answer = (
        "Multi-agent systems can separate responsibilities across specialized roles [1]. "
        "This second substantive claim deliberately has no citation attached to it.\n\n"
        "### Sources\n[1] Architecture source — https://example.com/source"
    )

    assert citation_coverage(answer) == pytest.approx(0.5)


def test_citation_validity_is_strict_about_sources_section() -> None:
    valid = _state(
        "Multi-agent systems can separate responsibilities across roles [1].\n\n"
        "### Sources\n[1] Architecture source — https://example.com/source"
    )
    invalid = _state("Multi-agent systems can separate responsibilities across roles [1].")

    assert citation_validity(valid) == 1.0
    assert citation_validity(invalid) == 0.0


def test_citation_validation_error_explains_strict_failure() -> None:
    invalid = _state("Multi-agent systems can separate responsibilities across roles [1].")

    error = citation_validation_error(invalid)

    assert error is not None
    assert "Sources section" in error
    assert citation_validity(invalid) == 0.0
