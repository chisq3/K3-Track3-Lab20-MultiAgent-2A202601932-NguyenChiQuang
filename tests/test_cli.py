import pytest
from typer.testing import CliRunner

from multi_agent_research_lab import cli
from multi_agent_research_lab.core.schemas import (
    CriticDecision,
    CriticResult,
    ResearchQuery,
    RouteName,
    RunStatus,
    SourceDocument,
)
from multi_agent_research_lab.core.state import ResearchState


def test_baseline_cli_renders_answer_and_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(request: ResearchQuery) -> ResearchState:
        state = ResearchState(request=request)
        state.status = RunStatus.COMPLETED
        state.final_answer = "A cited result [1]."
        state.sources = [
            SourceDocument(title="Source", url="https://example.com", snippet="Evidence")
        ]
        state.record_llm_usage(input_tokens=10, output_tokens=5, cost_usd=0.00001)
        state.record_step_duration("baseline_total", 0.25)
        state.trace_url = "https://smith.langchain.com/trace/baseline"
        return state

    monkeypatch.setattr(cli, "run_baseline", fake_run)

    result = CliRunner().invoke(
        cli.app,
        [
            "baseline",
            "--query",
            "Explain multi-agent systems",
            "--max-sources",
            "3",
            "--audience",
            "students",
        ],
    )

    assert result.exit_code == 0
    assert "A cited result [1]." in result.stdout
    assert "Status: completed" in result.stdout
    assert "Sources: 1" in result.stdout
    assert "Tokens: 15" in result.stdout
    assert "https://smith.langchain.com/trace/baseline" in result.stdout


def test_multi_agent_cli_renders_routes_and_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(request: ResearchQuery) -> ResearchState:
        state = ResearchState(request=request, status=RunStatus.COMPLETED)
        state.final_answer = "A multi-agent answer [1]."
        state.sources = [
            SourceDocument(title="Source", url="https://example.com", snippet="Evidence")
        ]
        for route in (RouteName.RESEARCHER, RouteName.ANALYST, RouteName.WRITER, RouteName.DONE):
            state.record_route(route)
        state.stop_reason = "completed"
        state.record_search_call()
        state.record_llm_usage(input_tokens=30, output_tokens=10, cost_usd=0.00004)
        state.record_step_duration("workflow_total", 0.5)
        state.trace_id = "trace-123"
        state.critic_result = CriticResult(
            decision=CriticDecision.PASS,
            quality_score=9,
            citation_coverage=1,
        )
        state.critic_history.append(state.critic_result)
        return state

    monkeypatch.setattr(cli, "run_multi_agent", fake_run)

    result = CliRunner().invoke(
        cli.app,
        ["multi-agent", "--query", "Explain multi-agent systems", "--max-sources", "3"],
    )

    assert result.exit_code == 0
    assert "A multi-agent answer [1]." in result.stdout
    assert "Routes: researcher" in result.stdout
    assert "writer -> done" in result.stdout
    assert "Status: completed" in result.stdout
    assert "Iterations: 4" in result.stdout
    assert "Calls: 1 search, 1 LLM" in result.stdout
    assert "Trace ID: trace-123" in result.stdout
    assert "Critic: pass, 1 review(s)" in result.stdout


def test_multi_agent_cli_returns_nonzero_for_failed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(request: ResearchQuery) -> ResearchState:
        return ResearchState(
            request=request,
            status=RunStatus.FAILED,
            stop_reason="researcher_failed",
            errors=["Researcher search returned no valid sources"],
        )

    monkeypatch.setattr(cli, "run_multi_agent", fake_run)

    result = CliRunner().invoke(
        cli.app,
        ["multi-agent", "--query", "Explain multi-agent systems"],
    )

    assert result.exit_code == 2
    assert "Multi-Agent Failed" in result.stdout
    assert "Researcher search returned no valid sources" in result.stdout
