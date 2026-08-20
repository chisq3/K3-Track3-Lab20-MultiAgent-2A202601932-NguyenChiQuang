"""Tests for deterministic offline corpus loading and retrieval."""

from pathlib import Path

import pytest

from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.evaluation.offline_corpus import (
    OfflineCorpus,
    OfflineCorpusSearchClient,
)

_CORPUS_DIR = Path("data/offline_benchmark")


def test_selected_corpus_contains_expected_topics() -> None:
    corpus = OfflineCorpus(_CORPUS_DIR)
    assert corpus.available_topic_ids() == ("AIAGENT-01", "AIAGENT-12", "AIAGENT-22")


def test_topic_builds_research_case_from_corpus_question() -> None:
    topic = OfflineCorpus(_CORPUS_DIR).load_topic("AIAGENT-01")
    case = topic.to_case(max_sources=5)
    assert case.case_id == "AIAGENT-01"
    assert "multi-agent" in case.query.lower()
    assert case.max_sources == 5


def test_offline_retrieval_is_deterministic_and_preserves_metadata() -> None:
    topic = OfflineCorpus(_CORPUS_DIR).load_topic("AIAGENT-12")
    client = OfflineCorpusSearchClient(topic)

    first = client.search(topic.topic.research_question, max_results=5)
    second = client.search(topic.topic.research_question, max_results=5)

    assert [source.url for source in first] == [source.url for source in second]
    assert len(first) == 5
    assert all(source.metadata["provider"] == "offline-corpus" for source in first)
    assert all(source.url and source.url.startswith("https://offline.local/") for source in first)
    assert any(source.metadata["is_synthetic"] is True for source in first)


def test_offline_retrieval_respects_max_results() -> None:
    topic = OfflineCorpus(_CORPUS_DIR).load_topic("AIAGENT-22")
    client = OfflineCorpusSearchClient(topic)
    assert len(client.search(topic.topic.research_question, max_results=3)) == 3


def test_unknown_topic_fails_clearly() -> None:
    corpus = OfflineCorpus(_CORPUS_DIR)
    with pytest.raises(ValidationError, match="Unknown offline topic"):
        corpus.load_topic("AIAGENT-99")
