import json

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.core.schemas import ResearchQuery, RunStatus
from multi_agent_research_lab.runners.multi_agent import run_multi_agent
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient, MockSearchClient
from tests.worker_samples import sample_sources


def test_multi_agent_runner_uses_injected_clients() -> None:
    llm = MockLLMClient(
        [
            LLMResponse(content="Research finding [1]."),
            LLMResponse(content="Evidence assessment [1]."),
            LLMResponse(
                content=(
                    "Final answer [1].\n\n## Sources\n"
                    "[1] Coordination through shared state — "
                    "https://example.com/shared-state"
                )
            ),
        ]
    )

    result = run_multi_agent(
        ResearchQuery(query="Explain multi-agent coordination"),
        settings=Settings(
            _env_file=None,
            LANGSMITH_TRACING=False,
            ENABLE_CRITIC=False,
        ),
        llm_client=llm,
        search_client=MockSearchClient(sample_sources()),
    )

    assert result.status is RunStatus.COMPLETED
    assert len(llm.calls) == 3


def test_multi_agent_runner_can_enable_critic_bonus() -> None:
    review = json.dumps(
        {
            "decision": "pass",
            "quality_score": 9,
            "citation_coverage": 1,
            "issues": [],
            "revision_instructions": None,
        }
    )
    llm = MockLLMClient(
        [
            LLMResponse(content="Research finding [1]."),
            LLMResponse(content="Evidence assessment [1]."),
            LLMResponse(
                content=(
                    "Final answer [1].\n\n## Sources\n"
                    "[1] Coordination through shared state â€” "
                    "https://example.com/shared-state"
                )
            ),
            LLMResponse(content=review),
        ]
    )

    result = run_multi_agent(
        ResearchQuery(query="Explain multi-agent coordination"),
        settings=Settings(
            _env_file=None,
            LANGSMITH_TRACING=False,
            ENABLE_CRITIC=True,
            MAX_ITERATIONS=6,
        ),
        llm_client=llm,
        search_client=MockSearchClient(sample_sources()),
    )

    assert result.status is RunStatus.COMPLETED
    assert result.critic_result is not None
    assert result.critic_result.decision.value == "pass"
    assert len(llm.calls) == 4


def test_multi_agent_runner_preserves_retry_headroom_with_one_revision() -> None:
    revise = json.dumps(
        {
            "decision": "revise",
            "quality_score": 6,
            "citation_coverage": 0.6,
            "issues": ["Clarify the evidence limitation."],
            "citation_issues": [],
            "unsupported_claims": [],
            "revision_instructions": "Add the supported limitation from source [1].",
        }
    )
    passed = json.dumps(
        {
            "decision": "pass",
            "quality_score": 9,
            "citation_coverage": 1,
            "issues": [],
            "citation_issues": [],
            "unsupported_claims": [],
            "revision_instructions": None,
        }
    )
    final_answer = (
        "Final answer with the supported limitation [1].\n\n## Sources\n"
        "[1] Coordination through shared state — https://example.com/shared-state"
    )
    llm = MockLLMClient(
        [
            LLMResponse(content="Research finding [1]."),
            LLMResponse(content="Invalid analyst citation [9]."),
            LLMResponse(content="Recovered evidence assessment [1]."),
            LLMResponse(content=final_answer),
            LLMResponse(content=revise),
            LLMResponse(content=final_answer),
            LLMResponse(content=passed),
        ]
    )

    result = run_multi_agent(
        ResearchQuery(query="Explain multi-agent coordination"),
        settings=Settings(
            _env_file=None,
            LANGSMITH_TRACING=False,
            ENABLE_CRITIC=True,
            MAX_ITERATIONS=6,
            MAX_REVISIONS=1,
        ),
        llm_client=llm,
        search_client=MockSearchClient(sample_sources()),
    )

    assert result.status is RunStatus.COMPLETED
    assert result.retry_count == 1
    assert result.revision_count == 1
    assert result.stop_reason == "completed"
    assert result.iteration == 8
    assert len(llm.calls) == 7
