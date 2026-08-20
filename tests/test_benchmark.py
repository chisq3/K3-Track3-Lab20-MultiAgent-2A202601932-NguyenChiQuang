import pytest

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.core.schemas import (
    BenchmarkCase,
    CriticDecision,
    CriticResult,
    ResearchQuery,
    RouteName,
    RunStatus,
    SourceDocument,
)
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation import benchmark
from multi_agent_research_lab.services.llm_client import LLMResponse
from tests.fakes import MockLLMClient


def _completed_state(
    request: ResearchQuery,
    *,
    critic: bool = False,
) -> ResearchState:
    state = ResearchState(request=request, status=RunStatus.COMPLETED)
    state.sources = [
        SourceDocument(
            title="Source",
            url="https://example.com/source",
            snippet="Evidence supports a comparison of agent architectures.",
        )
    ]
    state.final_answer = (
        "Agent architectures can be compared using the supplied evidence [1].\n\n"
        "### Sources\n[1] Source — https://example.com/source"
    )
    state.record_search_call()
    state.record_llm_usage(input_tokens=100, output_tokens=40, cost_usd=0.0002)
    state.stop_reason = "completed"
    if critic:
        state.critic_history.append(
            CriticResult(
                decision=CriticDecision.PASS,
                quality_score=9,
                citation_coverage=1,
            )
        )
    return state


def _judge_responses(count: int) -> list[LLMResponse]:
    payload = (
        '{"relevance": 2, "completeness": 2, "factual_grounding": 2, '
        '"citation_correctness": 2, "clarity": 2, "rationale": "Strong."}'
    )
    return [LLMResponse(content=payload, input_tokens=50, output_tokens=20) for _ in range(count)]


def test_run_benchmark_captures_failure_instead_of_raising() -> None:
    case = BenchmarkCase(case_id="failure", query="Explain a benchmark failure")

    def failing_runner(_request: ResearchQuery) -> ResearchState:
        raise RuntimeError("provider unavailable")

    state, metrics = benchmark.run_benchmark("baseline", case, failing_runner)

    assert state.status is RunStatus.FAILED
    assert metrics.status is RunStatus.FAILED
    assert metrics.failure_rate == 1.0
    assert metrics.stop_reason == "runner_exception"
    assert "provider unavailable" in metrics.notes


def test_suite_separates_core_and_critic_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, bool]] = []

    def fake_baseline(
        request: ResearchQuery,
        *,
        settings: Settings,
    ) -> ResearchState:
        observed.append(("baseline", settings.enable_critic))
        return _completed_state(request)

    def fake_multi(
        request: ResearchQuery,
        *,
        settings: Settings,
    ) -> ResearchState:
        observed.append(("multi", settings.enable_critic))
        state = _completed_state(request, critic=settings.enable_critic)
        for route in (RouteName.RESEARCHER, RouteName.ANALYST, RouteName.WRITER):
            state.record_route(route)
        if settings.enable_critic:
            state.record_route(RouteName.CRITIC)
        state.record_route(RouteName.DONE)
        return state

    monkeypatch.setattr(benchmark, "run_baseline", fake_baseline)
    monkeypatch.setattr(benchmark, "run_multi_agent", fake_multi)

    metrics = benchmark.run_benchmark_suite(
        [BenchmarkCase(case_id="q1", query="Compare agent benchmark architectures")],
        repeats=1,
        settings=Settings(_env_file=None, ENABLE_CRITIC=True),
        judge_llm_client=MockLLMClient(_judge_responses(3)),
    )

    assert [item.run_name for item in metrics] == [
        "baseline",
        "multi-agent",
        "multi-agent-critic",
    ]
    assert observed == [("baseline", False), ("multi", False), ("multi", True)]
    assert all(item.quality_score == 10 for item in metrics)
    assert all(item.citation_coverage == 1 for item in metrics)
    assert metrics[1].critic_decision is None
    assert metrics[2].critic_decision is CriticDecision.PASS


def test_suite_rotates_variant_order_between_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_baseline(
        request: ResearchQuery,
        *,
        settings: Settings,
    ) -> ResearchState:
        return _completed_state(request)

    def fake_multi(
        request: ResearchQuery,
        *,
        settings: Settings,
    ) -> ResearchState:
        return _completed_state(request, critic=settings.enable_critic)

    monkeypatch.setattr(benchmark, "run_baseline", fake_baseline)
    monkeypatch.setattr(benchmark, "run_multi_agent", fake_multi)

    metrics = benchmark.run_benchmark_suite(
        [BenchmarkCase(case_id="q1", query="Compare agent benchmark architectures")],
        repeats=2,
        settings=Settings(_env_file=None),
        judge_llm_client=MockLLMClient(_judge_responses(6)),
    )

    assert [item.run_name for item in metrics[:3]] == [
        "baseline",
        "multi-agent",
        "multi-agent-critic",
    ]
    assert [item.run_name for item in metrics[3:]] == [
        "multi-agent",
        "multi-agent-critic",
        "baseline",
    ]
