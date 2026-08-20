from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.core.schemas import ResearchQuery, RunStatus, SourceDocument
from multi_agent_research_lab.runners.baseline import run_baseline
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient, MockSearchClient


def test_runner_uses_injected_clients_without_network() -> None:
    llm = MockLLMClient([LLMResponse(content="Result [1]", input_tokens=10, output_tokens=4)])
    search = MockSearchClient(
        [
            SourceDocument(
                title="Source",
                url="https://example.com/source",
                snippet="Evidence",
            )
        ]
    )

    state = run_baseline(
        ResearchQuery(query="Explain agent orchestration"),
        settings=Settings(_env_file=None, LANGSMITH_TRACING=False),
        llm_client=llm,
        search_client=search,
    )

    assert state.status is RunStatus.COMPLETED
    assert state.final_answer == "Result [1]"
    assert len(llm.calls) == 1
    assert len(search.calls) == 1
