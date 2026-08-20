"""Deterministic retrieval adapter for the selected offline research corpus."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import BenchmarkCase, SourceDocument
from multi_agent_research_lab.observability.tracing import trace_span

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]+")
_STOPWORDS = {
    "about",
    "after",
    "against",
    "among",
    "and",
    "are",
    "for",
    "from",
    "how",
    "into",
    "its",
    "more",
    "should",
    "than",
    "that",
    "the",
    "their",
    "this",
    "through",
    "what",
    "when",
    "which",
    "with",
}


class CorpusMetadata(BaseModel):
    """Minimal benchmark metadata required by the offline adapter."""

    model_config = ConfigDict(extra="allow")

    benchmark_name: str
    benchmark_version: str
    topic_id: str
    topic_number: int


class TopicInfo(BaseModel):
    """Human-facing topic fields used to construct a benchmark case."""

    model_config = ConfigDict(extra="allow")

    name: str
    research_question: str
    target_audience: str


class CorpusSource(BaseModel):
    """Citation-ready source document embedded in one corpus topic."""

    model_config = ConfigDict(extra="allow")

    document_id: str
    title: str
    document_class: str
    is_synthetic: bool
    citation_label: str
    full_text: str
    provenance_url: str | None = None
    recommended_weight: str | None = None


class KnowledgeBase(BaseModel):
    """Subset of the topic knowledge base used by the retrieval adapter."""

    model_config = ConfigDict(extra="allow")

    source_documents: list[CorpusSource] = Field(min_length=1)


class OfflineTopic(BaseModel):
    """Validated topic payload loaded from the lab-provided corpus."""

    model_config = ConfigDict(extra="allow")

    benchmark_metadata: CorpusMetadata
    topic: TopicInfo
    knowledge_base: KnowledgeBase

    def to_case(self, *, max_sources: int = 5) -> BenchmarkCase:
        """Create the same ResearchQuery-compatible case for every architecture."""

        return BenchmarkCase(
            case_id=self.benchmark_metadata.topic_id,
            query=self.topic.research_question,
            audience=self.topic.target_audience,
            max_sources=max_sources,
        )


class OfflineCorpus:
    """Load selected corpus topics from a stable repository directory."""

    def __init__(self, corpus_dir: Path | str) -> None:
        self.corpus_dir = Path(corpus_dir)
        self.topics_dir = self.corpus_dir / "topics"
        if not self.topics_dir.is_dir():
            raise ValidationError(
                f"Offline corpus topics directory does not exist: {self.topics_dir}"
            )
        self._topic_paths = self._discover_topics()

    def available_topic_ids(self) -> tuple[str, ...]:
        """Return stable topic IDs available in this selected corpus."""

        return tuple(sorted(self._topic_paths))

    def load_topic(self, topic_id: str) -> OfflineTopic:
        """Load and validate one selected topic by its canonical AIAGENT ID."""

        normalized = topic_id.strip().upper()
        path = self._topic_paths.get(normalized)
        if path is None:
            available = ", ".join(self.available_topic_ids()) or "none"
            raise ValidationError(
                f"Unknown offline topic {topic_id!r}; available topics: {available}"
            )

        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
            return OfflineTopic.model_validate(raw)
        except (OSError, json.JSONDecodeError, PydanticValidationError) as exc:
            raise ValidationError(f"Invalid offline corpus topic: {path.name}") from exc

    def _discover_topics(self) -> dict[str, Path]:
        topic_paths: dict[str, Path] = {}
        for path in sorted(self.topics_dir.glob("*.json")):
            try:
                raw: object = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    continue
                metadata = raw.get("benchmark_metadata")
                if not isinstance(metadata, dict):
                    continue
                topic_id = metadata.get("topic_id")
                if not isinstance(topic_id, str) or not topic_id.strip():
                    continue
                topic_paths[topic_id.strip().upper()] = path
            except (OSError, json.JSONDecodeError):
                continue
        if not topic_paths:
            raise ValidationError(f"No valid topic JSON files found in {self.topics_dir}")
        return topic_paths


class OfflineCorpusSearchClient:
    """Deterministic SearchClient-compatible retrieval over one offline topic."""

    def __init__(self, topic: OfflineTopic) -> None:
        self.topic = topic
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        """Rank embedded source documents without Tavily or any network retrieval."""

        clean_query = query.strip()
        if not clean_query:
            raise ValidationError("offline search query must not be empty")
        if not 1 <= max_results <= 20:
            raise ValidationError("max_results must be between 1 and 20")

        self.calls.append((clean_query, max_results))
        selected = self._ranked_sources(clean_query)[:max_results]
        topic_id = self.topic.benchmark_metadata.topic_id

        with trace_span(
            "offline-corpus-search",
            {
                "query": clean_query,
                "max_results": max_results,
                "topic_id": topic_id,
                "corpus_version": self.topic.benchmark_metadata.benchmark_version,
            },
            run_type="retriever",
        ) as span:
            documents = [self._to_source_document(source) for source in selected]
            span["outputs"] = {
                "source_count": len(documents),
                "sources": [
                    {
                        "document_id": document.metadata.get("document_id"),
                        "title": document.title,
                        "is_synthetic": document.metadata.get("is_synthetic"),
                    }
                    for document in documents
                ],
            }
            return documents

    def selected_source_metadata(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Return deterministic retrieval metadata for benchmark reproducibility evidence."""

        if not 1 <= max_results <= 20:
            raise ValidationError("max_results must be between 1 and 20")
        selected = self._ranked_sources(query.strip())[:max_results]
        return [
            {
                "document_id": source.document_id,
                "citation_label": source.citation_label,
                "title": source.title,
                "document_class": source.document_class,
                "is_synthetic": source.is_synthetic,
                "provenance_url": source.provenance_url,
            }
            for source in selected
        ]

    def _ranked_sources(self, query: str) -> list[CorpusSource]:
        query_tokens = _tokens(query)
        scored: list[tuple[int, str, CorpusSource]] = []
        for source in self.topic.knowledge_base.source_documents:
            title_overlap = len(query_tokens & _tokens(source.title))
            body_overlap = len(query_tokens & _tokens(source.full_text))
            score = (title_overlap * 5) + body_overlap
            scored.append((score, source.document_id.lower(), source))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored]

    def _to_source_document(self, source: CorpusSource) -> SourceDocument:
        topic_id = self.topic.benchmark_metadata.topic_id
        synthetic_prefix = "[SYNTHETIC] " if source.is_synthetic else ""
        synthetic_label = "yes" if source.is_synthetic else "no"
        snippet = (
            f"Corpus source ID: {source.document_id}\n"
            f"Document class: {source.document_class}\n"
            f"Synthetic evidence: {synthetic_label}\n\n"
            f"{source.full_text.strip()}"
        )
        return SourceDocument(
            title=f"{synthetic_prefix}{source.title}",
            url=f"https://offline.local/{topic_id}/{_safe_locator(source.document_id)}",
            snippet=snippet,
            metadata={
                "provider": "offline-corpus",
                "corpus_version": self.topic.benchmark_metadata.benchmark_version,
                "topic_id": topic_id,
                "document_id": source.document_id,
                "citation_label": source.citation_label,
                "document_class": source.document_class,
                "is_synthetic": source.is_synthetic,
                "provenance_url": source.provenance_url,
                "recommended_weight": source.recommended_weight,
            },
        )


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _safe_locator(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._~-]+", "-", value.strip())
    return clean or "source"
