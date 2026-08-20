"""Shared source formatting and citation validation for grounded agents."""

import re

from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import SourceDocument

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_URL_PATTERN = re.compile(r"https?://[^\s<>\])}]+")


def format_numbered_sources(sources: list[SourceDocument]) -> str:
    """Render sources once while preserving stable citation numbers."""

    return "\n\n".join(
        f"[{index}] {source.title}\nURL: {source.url or 'Unavailable'}\nEvidence: {source.snippet}"
        for index, source in enumerate(sources, start=1)
    )


def extract_citation_ids(text: str) -> set[int]:
    return {int(match) for match in _CITATION_PATTERN.findall(text)}


def validate_grounded_text(
    text: str,
    sources: list[SourceDocument],
    *,
    require_sources_section: bool = False,
    require_cited_urls: bool = False,
) -> set[int]:
    """Validate that citations and URLs only reference supplied sources."""

    clean_text = text.strip()
    if not clean_text:
        raise ValidationError("Agent output must not be empty")
    if not sources:
        raise ValidationError("Grounded output requires at least one source")

    sources_match = re.search(r"(?im)^#{0,3}\s*sources\s*$", clean_text)
    citation_scope = clean_text[: sources_match.start()] if sources_match else clean_text
    citation_ids = extract_citation_ids(citation_scope)
    if not citation_ids:
        raise ValidationError("Agent output must contain at least one source citation")

    valid_ids = set(range(1, len(sources) + 1))
    invalid_ids = sorted(citation_ids - valid_ids)
    if invalid_ids:
        raise ValidationError(f"Agent output contains invalid citation IDs: {invalid_ids}")

    if require_sources_section and sources_match is None:
        raise ValidationError("Final answer must contain a Sources section")

    allowed_urls = {source.url for source in sources if source.url}
    output_urls = {match.rstrip(".,;:") for match in _URL_PATTERN.findall(clean_text)}
    unknown_urls = sorted(output_urls - allowed_urls)
    if unknown_urls:
        raise ValidationError("Agent output contains a URL that is not in the supplied sources")

    if require_cited_urls:
        if sources_match is None:
            raise ValidationError("Cited URLs require a Sources section")
        sources_section = clean_text[sources_match.end() :]
        missing_urls: list[int] = []
        missing_labels: list[int] = []
        cited_urls: set[str] = set()
        for citation_id in sorted(citation_ids):
            source_url = sources[citation_id - 1].url
            if source_url is not None:
                cited_urls.add(source_url)
                if source_url not in sources_section:
                    missing_urls.append(citation_id)
            if f"[{citation_id}]" not in sources_section:
                missing_labels.append(citation_id)
        if missing_urls:
            raise ValidationError(
                f"Sources section is missing URLs for cited source IDs: {missing_urls}"
            )
        if missing_labels:
            raise ValidationError(
                f"Sources section is missing citation labels for source IDs: {missing_labels}"
            )
        section_urls = {match.rstrip(".,;:") for match in _URL_PATTERN.findall(sources_section)}
        if section_urls - cited_urls:
            raise ValidationError("Sources section contains uncited source URLs")

    return citation_ids
