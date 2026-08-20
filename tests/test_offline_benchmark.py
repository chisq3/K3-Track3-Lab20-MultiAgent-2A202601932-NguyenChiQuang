"""Small regression tests for offline benchmark configuration."""

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.evaluation.benchmark import (
    BASELINE,
    MULTI_AGENT,
    MULTI_AGENT_CRITIC,
)
from multi_agent_research_lab.evaluation.offline_benchmark import (
    DEFAULT_OFFLINE_TOPICS,
    _variant_settings,
)


def test_default_offline_topics_match_selected_coursework_subset() -> None:
    assert DEFAULT_OFFLINE_TOPICS == ("AIAGENT-01", "AIAGENT-12", "AIAGENT-22")


def test_offline_variants_force_critic_on_and_off_independently_of_shell() -> None:
    settings = Settings(_env_file=None, ENABLE_CRITIC=True, MAX_REVISIONS=1)
    variants = _variant_settings(settings)

    assert variants[BASELINE].enable_critic is False
    assert variants[MULTI_AGENT].enable_critic is False
    assert variants[MULTI_AGENT_CRITIC].enable_critic is True
    assert variants[MULTI_AGENT_CRITIC].max_revisions == 1
