from pathlib import Path

from multi_agent_research_lab.core.schemas import BenchmarkMetrics, RunStatus
from multi_agent_research_lab.evaluation.report import (
    render_markdown_report,
    summarize_metrics,
    write_benchmark_outputs,
)


def _metric(
    run_name: str,
    latency: float,
    quality: float,
    *,
    failed: bool = False,
) -> BenchmarkMetrics:
    return BenchmarkMetrics(
        run_name=run_name,
        query_id="q1",
        status=RunStatus.FAILED if failed else RunStatus.COMPLETED,
        latency_seconds=latency,
        total_tokens=100,
        estimated_cost_usd=0.001,
        quality_score=quality,
        citation_coverage=0.8,
        citation_validity=1.0,
        failure_rate=1.0 if failed else 0.0,
    )


def test_report_renders_markdown() -> None:
    metrics = [
        _metric("baseline", 1.0, 7.0),
        _metric("multi-agent", 2.0, 8.0),
        _metric("multi-agent-critic", 2.5, 8.5),
    ]

    report = render_markdown_report(metrics)

    assert "# Báo cáo Benchmark Online" in report
    assert "## Kết quả Tổng hợp" in report
    assert "baseline" in report
    assert "multi-agent-critic" in report
    assert "## Trade-off Quan sát được" in report
    assert "## Diễn giải End-to-End" in report
    assert "independent blind judge" in report


def test_summary_calculates_failure_rate_and_means() -> None:
    summaries = summarize_metrics(
        [
            _metric("baseline", 1.0, 7.0),
            _metric("baseline", 3.0, 9.0, failed=True),
        ]
    )

    assert len(summaries) == 1
    assert summaries[0].runs == 2
    assert summaries[0].success_rate == 0.5
    assert summaries[0].failure_rate == 0.5
    assert summaries[0].avg_latency_seconds == 2.0
    assert summaries[0].avg_quality_score == 8.0


def test_write_benchmark_outputs_creates_three_artifacts(tmp_path: Path) -> None:
    paths = write_benchmark_outputs(
        [
            _metric("baseline", 1.0, 7.0),
            _metric("multi-agent", 2.0, 8.0),
        ],
        output_dir=tmp_path,
    )

    assert {path.name for path in paths} == {
        "benchmark_raw.jsonl",
        "benchmark_summary.csv",
        "benchmark_report.md",
    }
    assert all(path.exists() for path in paths)
    assert "baseline" in (tmp_path / "benchmark_summary.csv").read_text(encoding="utf-8")
