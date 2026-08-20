"""Tổng hợp benchmark và tạo artifact báo cáo."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from statistics import mean

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.core.schemas import (
    BenchmarkMetrics,
    BenchmarkSummary,
    RunStatus,
)


def summarize_metrics(metrics: list[BenchmarkMetrics]) -> list[BenchmarkSummary]:
    """Tổng hợp các lần chạy lặp theo kiến trúc."""

    if not metrics:
        return []

    grouped: dict[str, list[BenchmarkMetrics]] = defaultdict(list)
    for item in metrics:
        grouped[item.run_name].append(item)

    summaries: list[BenchmarkSummary] = []
    for run_name, items in grouped.items():
        runs = len(items)
        completed = sum(item.status is RunStatus.COMPLETED for item in items)
        summaries.append(
            BenchmarkSummary(
                run_name=run_name,
                runs=runs,
                success_rate=completed / runs,
                failure_rate=1 - (completed / runs),
                avg_latency_seconds=mean(item.latency_seconds for item in items),
                avg_total_tokens=mean(item.total_tokens for item in items),
                avg_estimated_cost_usd=_all_or_none_average(
                    item.estimated_cost_usd for item in items
                ),
                avg_quality_score=_available_average(item.quality_score for item in items),
                avg_citation_coverage=_available_average(item.citation_coverage for item in items),
                avg_citation_validity=_available_average(item.citation_validity for item in items),
                avg_iterations=mean(item.iterations for item in items),
                avg_revisions=mean(item.revision_count for item in items),
            )
        )
    order = {"baseline": 0, "multi-agent": 1, "multi-agent-critic": 2}
    return sorted(summaries, key=lambda item: (order.get(item.run_name, 99), item.run_name))


def render_markdown_report(
    metrics: list[BenchmarkMetrics],
    *,
    settings: Settings | None = None,
) -> str:
    """Render báo cáo benchmark Markdown tự chứa từ raw run metrics."""

    summaries = summarize_metrics(metrics)
    lines = [
        "# Báo cáo Benchmark Online",
        "",
        f"Ngày tạo benchmark: {date.today().isoformat()}",
        "",
        "## Thiết lập Thí nghiệm",
        "",
        f"- Model: `{settings.openai_model if settings is not None else 'không ghi nhận'}`.",
        "- LLM endpoint: `"
        f"{settings.openai_base_url if settings is not None else 'không ghi nhận'}`.",
        "- Search provider: Tavily thông qua `SearchClient` của repo.",
        "- Temperature: baseline 0.2; Researcher 0.2; Analyst 0.1; Writer 0.4; "
        "Critic 0.0; blind quality judge 0.0.",
        "- Cost ưu tiên provider-reported usage từ OpenRouter; nếu cost không đầy đủ thì "
        "ghi `n/a`, không tự áp giá của provider khác.",
        "",
        "### Bộ test",
        "",
        "| Case | Query | Đối tượng | Số nguồn tối đa |",
        "|---|---|---|---:|",
    ]
    for case_id, query, audience, max_sources in _unique_cases(metrics):
        escaped_query = query.replace("|", "\\|")
        escaped_audience = audience.replace("|", "\\|")
        lines.append(f"| {case_id} | {escaped_query} | {escaped_audience} | {max_sources} |")

    lines.extend(
        [
            "",
            "## Phương pháp",
            "",
            "- So sánh `baseline`, `multi-agent` và `multi-agent-critic` trên cùng bộ case.",
            "- Thứ tự variant được xoay giữa các repeat để giảm bias latency do thứ tự chạy.",
            "- Quality được chấm bằng cùng một blind LLM judge 0–10 cho mọi kiến trúc.",
            "- Citation coverage là proxy deterministic ở mức câu: số câu nội dung có "
            "inline citation `[n]` chia cho tổng số câu nội dung.",
            "- Citation validity dùng tiêu chí strict: citation ID và source URL cuối "
            "phải khớp source set đã cung cấp.",
            "- Cost/tokens của kiến trúc không tính independent quality-judge call; "
            "usage của judge được lưu riêng trong raw results.",
            "- Một run chỉ được tính thành công khi final status là `completed`; "
            "`partial` được tính vào failure rate.",
            "",
            "## Kết quả Tổng hợp",
            "",
            "| Kiến trúc | Runs | Thành công | Latency (s) | Tokens | Cost (USD) | Quality /10 | "
            "Citation coverage | Citation validity | Iterations | Revisions |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in summaries:
        lines.append(
            f"| {summary.run_name} | {summary.runs} | {summary.success_rate:.0%} | "
            f"{summary.avg_latency_seconds:.2f} | {summary.avg_total_tokens:.0f} | "
            f"{_fmt_cost(summary.avg_estimated_cost_usd)} | "
            f"{_fmt_score(summary.avg_quality_score)} | "
            f"{_fmt_percent(summary.avg_citation_coverage)} | "
            f"{_fmt_percent(summary.avg_citation_validity)} | "
            f"{summary.avg_iterations:.1f} | {summary.avg_revisions:.2f} |"
        )

    lines.extend(_render_tradeoffs(summaries))
    lines.extend(
        [
            "",
            "## Kết quả Từng Run",
            "",
            "| Kiến trúc | Query | Repeat | Trạng thái | Latency (s) | Tokens | Cost | Quality | "
            "Citation coverage | Hợp lệ | Retries | Revisions | Lý do dừng | Trace |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for metric in metrics:
        trace = f"[trace]({metric.trace_url})" if metric.trace_url else (metric.trace_id or "")
        lines.append(
            f"| {metric.run_name} | {metric.query_id} | {metric.repeat} | "
            f"{metric.status.value} | {metric.latency_seconds:.2f} | "
            f"{metric.total_tokens} | {_fmt_cost(metric.estimated_cost_usd)} | "
            f"{_fmt_score(metric.quality_score)} | "
            f"{_fmt_percent(metric.citation_coverage)} | "
            f"{_fmt_percent(metric.citation_validity)} | {metric.retry_count} | "
            f"{metric.revision_count} | {metric.stop_reason or ''} | {trace} |"
        )

    lines.extend(_render_failures(metrics))
    lines.extend(_render_end_to_end(metrics))
    lines.extend(
        [
            "",
            "## Ghi chú Diễn giải",
            "",
            "Không giả định multi-agent luôn tốt hơn. "
            "Kiến trúc đắt hơn chỉ hợp lý khi lợi ích về grounding, "
            "citation, auditability hoặc failure handling đủ quan trọng với bài toán mục tiêu.",
            "",
            "Kết quả Critic trong workflow chỉ mang tính diagnostic. Cột "
            "quality aggregate dùng independent blind judge, vì vậy Critic không "
            "tự chấm điểm cho chính variant của mình.",
            "",
        ]
    )
    return "\n".join(lines)


def write_benchmark_outputs(
    metrics: list[BenchmarkMetrics],
    *,
    output_dir: Path = Path("reports"),
    settings: Settings | None = None,
) -> tuple[Path, Path, Path]:
    """Ghi raw JSONL, aggregate CSV và báo cáo Markdown bắt buộc."""

    if not metrics:
        raise ValueError("cannot write benchmark outputs without metrics")

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "benchmark_raw.jsonl"
    summary_path = output_dir / "benchmark_summary.csv"
    report_path = output_dir / "benchmark_report.md"

    with raw_path.open("w", encoding="utf-8") as handle:
        for metric in metrics:
            handle.write(json.dumps(metric.model_dump(mode="json"), ensure_ascii=False) + "\n")

    summaries = summarize_metrics(metrics)
    fieldnames = list(BenchmarkSummary.model_fields)
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(summary.model_dump(mode="json"))

    report_path.write_text(
        render_markdown_report(metrics, settings=settings),
        encoding="utf-8",
    )
    return raw_path, summary_path, report_path


def _unique_cases(metrics: list[BenchmarkMetrics]) -> list[tuple[str, str, str, int]]:
    seen: set[str] = set()
    cases: list[tuple[str, str, str, int]] = []
    for item in metrics:
        if not item.query_id or item.query_id in seen:
            continue
        seen.add(item.query_id)
        cases.append((item.query_id, item.query, item.audience, item.max_sources))
    return cases


def _render_tradeoffs(summaries: list[BenchmarkSummary]) -> list[str]:
    by_name = {item.run_name: item for item in summaries}
    lines = ["", "## Trade-off Quan sát được", ""]

    baseline = by_name.get("baseline")
    multi = by_name.get("multi-agent")
    critic = by_name.get("multi-agent-critic")

    if baseline is not None and multi is not None:
        citation_delta = _fmt_point_delta(
            baseline.avg_citation_coverage,
            multi.avg_citation_coverage,
            percent=True,
        )
        lines.append(
            "- Multi-agent so với baseline: "
            f"latency {_fmt_delta(baseline.avg_latency_seconds, multi.avg_latency_seconds)}, "
            f"tokens {_fmt_delta(baseline.avg_total_tokens, multi.avg_total_tokens)}, "
            f"quality {_fmt_point_delta(baseline.avg_quality_score, multi.avg_quality_score)}, "
            f"citation coverage {citation_delta}."
        )
    if multi is not None and critic is not None:
        citation_delta = _fmt_point_delta(
            multi.avg_citation_coverage,
            critic.avg_citation_coverage,
            percent=True,
        )
        lines.append(
            "- Critic so với core multi-agent: "
            f"latency {_fmt_delta(multi.avg_latency_seconds, critic.avg_latency_seconds)}, "
            f"tokens {_fmt_delta(multi.avg_total_tokens, critic.avg_total_tokens)}, "
            f"quality {_fmt_point_delta(multi.avg_quality_score, critic.avg_quality_score)}, "
            f"citation coverage {citation_delta}."
        )
    if len(lines) == 3:
        lines.append("- Không đủ summary của các variant để tính trade-off.")
    return lines


def _render_failures(metrics: list[BenchmarkMetrics]) -> list[str]:
    failed = [item for item in metrics if item.status is not RunStatus.COMPLETED]
    lines = ["", "## Phân tích Failure", ""]
    if not failed:
        lines.append(
            "Không có run benchmark nào kết thúc ở `partial` hoặc `failed`. Dùng trace "
            "LangSmith Writer/citation retry đã lưu làm failure-mode evidence cụ thể."
        )
        return lines

    lines.extend(
        [
            "| Kiến trúc | Query | Repeat | Trạng thái | Lý do dừng | Ghi chú |",
            "|---|---|---:|---|---|---|",
        ]
    )
    for item in failed:
        notes = _localize_failure_notes(item.notes).replace("|", "\\|")
        lines.append(
            f"| {item.run_name} | {item.query_id} | {item.repeat} | {item.status.value} | "
            f"{item.stop_reason or ''} | {notes} |"
        )
    return lines


def _localize_failure_notes(notes: str) -> str:
    """Dịch các failure note chuẩn sang Tiếng Việt để report dễ đọc."""

    return (
        notes.replace(
            "Sources section contains uncited source URLs",
            "Phần Sources chứa URL của nguồn không được trích dẫn",
        )
        .replace(
            "Sources section is missing citation labels for source IDs:",
            "Phần Sources thiếu citation label cho source ID:",
        )
        .replace(
            "Critic revise decision requires at least one issue",
            "Quyết định revise của Critic phải kèm ít nhất một vấn đề cần sửa",
        )
    )


def _render_end_to_end(metrics: list[BenchmarkMetrics]) -> list[str]:
    """Render valid-completed rate và lưu ý về cách đọc quality."""

    grouped: dict[str, list[BenchmarkMetrics]] = defaultdict(list)
    for item in metrics:
        grouped[item.run_name].append(item)

    order = ("baseline", "multi-agent", "multi-agent-critic")
    lines = [
        "",
        "## Diễn giải End-to-End",
        "",
        "Metric **valid completed rate** được định nghĩa là tỷ lệ run vừa `completed` "
        "vừa đạt strict `citation_validity == 1`.",
        "",
        "| Kiến trúc | Valid completed |",
        "|---|---:|",
    ]
    for run_name in order:
        items = grouped.get(run_name)
        if not items:
            continue
        valid_completed = sum(
            item.status is RunStatus.COMPLETED and item.citation_validity == 1.0 for item in items
        )
        lines.append(
            f"| {run_name} | {valid_completed}/{len(items)} = {valid_completed / len(items):.1%} |"
        )

    lines.extend(
        [
            "",
            "Quality cần được đọc thận trọng: run `failed` không có quality score nên "
            "average quality có thể chịu **survivorship bias**. Judge 0–10 cũng có thể "
            "gặp **ceiling effect** khi nhiều output hoàn thành đều đạt điểm rất cao.",
            "",
            "Vì vậy kết luận benchmark phải đọc cùng completion rate, citation validity, "
            "latency, tokens, cost, retry và failure modes.",
        ]
    )
    return lines


def _available_average(values: Iterable[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return mean(available) if available else None


def _all_or_none_average(values: Iterable[float | None]) -> float | None:
    collected = list(values)
    if not collected or any(value is None for value in collected):
        return None
    return mean(value for value in collected if value is not None)


def _fmt_cost(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6f}"


def _fmt_score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _fmt_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _fmt_delta(before: float, after: float) -> str:
    if before == 0:
        return "n/a"
    change = ((after - before) / before) * 100
    return f"{change:+.1f}%"


def _fmt_point_delta(
    before: float | None,
    after: float | None,
    *,
    percent: bool = False,
) -> str:
    if before is None or after is None:
        return "n/a"
    delta = after - before
    if percent:
        return f"{delta:+.1%} điểm phần trăm"
    return f"{delta:+.2f} điểm"
