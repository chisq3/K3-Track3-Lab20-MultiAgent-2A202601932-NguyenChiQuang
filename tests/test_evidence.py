import pytest

from multi_agent_research_lab.agents.evidence import (
    format_numbered_sources,
    validate_grounded_text,
)
from multi_agent_research_lab.core.errors import ValidationError
from tests.worker_samples import sample_sources


def test_formats_sources_with_stable_citation_numbers() -> None:
    rendered = format_numbered_sources(sample_sources())

    assert "[1] Coordination through shared state" in rendered
    assert "[2] Multi-agent system trade-offs" in rendered


def test_validates_grounded_final_answer() -> None:
    answer = (
        "Shared state supports coordination [1].\n\n"
        "## Sources\n"
        "[1] Coordination through shared state — https://example.com/shared-state"
    )

    citation_ids = validate_grounded_text(
        answer,
        sample_sources(),
        require_sources_section=True,
        require_cited_urls=True,
    )

    assert citation_ids == {1}


def test_rejects_invalid_citation_id() -> None:
    with pytest.raises(ValidationError, match="invalid citation IDs"):
        validate_grounded_text("Unsupported claim [3].", sample_sources())


def test_rejects_invented_url() -> None:
    answer = (
        "Shared state supports coordination [1].\n\n"
        "## Sources\n"
        "[1] Fake — https://invented.example/fake\n"
        "https://example.com/shared-state"
    )

    with pytest.raises(ValidationError, match="URL that is not"):
        validate_grounded_text(
            answer,
            sample_sources(),
            require_sources_section=True,
            require_cited_urls=True,
        )


def test_rejects_unlabelled_sources_section() -> None:
    answer = (
        "Shared state supports coordination [1].\n\n"
        "## Sources\n"
        "Coordination through shared state — https://example.com/shared-state"
    )

    with pytest.raises(ValidationError, match="missing citation labels"):
        validate_grounded_text(
            answer,
            sample_sources(),
            require_sources_section=True,
            require_cited_urls=True,
        )


def test_rejects_uncited_source_in_sources_section() -> None:
    answer = (
        "Shared state supports coordination [1].\n\n"
        "## Sources\n"
        "[1] Coordination — https://example.com/shared-state\n"
        "[2] Trade-offs — https://example.com/trade-offs"
    )

    with pytest.raises(ValidationError, match="uncited source URLs"):
        validate_grounded_text(
            answer,
            sample_sources(),
            require_sources_section=True,
            require_cited_urls=True,
        )
