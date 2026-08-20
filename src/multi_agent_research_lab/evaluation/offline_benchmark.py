"""Benchmark có kiểm soát trên subset corpus offline do lab cung cấp."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from multi_agent_research_lab.agents.protocols import LLMCompletionClient
from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import BenchmarkMetrics, ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.benchmark import (
    BASELINE,
    MULTI_AGENT,
    MULTI_AGENT_CRITIC,
    Evaluator,
    run_benchmark,
)
from multi_agent_research_lab.evaluation.evaluator import QualityJudge
from multi_agent_research_lab.evaluation.offline_corpus import (
    OfflineCorpus,
    OfflineCorpusSearchClient,
    OfflineTopic,
)
from multi_agent_research_lab.evaluation.report import write_benchmark_outputs
from multi_agent_research_lab.runners import run_baseline, run_multi_agent
from multi_agent_research_lab.services.llm_client import LLMClient

Progress = Callable[[str], None]
Runner = Callable[[ResearchQuery], ResearchState]

DEFAULT_OFFLINE_TOPICS = ("AIAGENT-01", "AIAGENT-12", "AIAGENT-22")
_VARIANTS = (BASELINE, MULTI_AGENT, MULTI_AGENT_CRITIC)


def run_offline_benchmark_suite(
    topic_ids: Sequence[str] = DEFAULT_OFFLINE_TOPICS,
    *,
    corpus_dir: Path = Path("data/offline_benchmark"),
    repeats: int = 2,
    max_sources: int = 5,
    settings: Settings | None = None,
    judge_llm_client: LLMCompletionClient | None = None,
    progress: Progress | None = None,
) -> tuple[list[BenchmarkMetrics], list[OfflineTopic]]:
    """Chạy ba kiến trúc trên deterministic evidence từ các corpus topic đã chọn."""

    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if not 1 <= max_sources <= 20:
        raise ValueError("max_sources must be between 1 and 20")
    if not topic_ids:
        raise ValueError("offline benchmark requires at least one topic")

    runtime_settings = settings or get_settings()
    corpus = OfflineCorpus(corpus_dir)
    topics = [corpus.load_topic(topic_id) for topic_id in topic_ids]

    if judge_llm_client is not None:
        judge = QualityJudge(judge_llm_client)
        metrics = _execute_suite(
            topics,
            repeats=repeats,
            max_sources=max_sources,
            settings=runtime_settings,
            evaluator=judge.evaluate,
            progress=progress,
        )
        return metrics, topics

    with LLMClient(runtime_settings) as judge_client:
        judge = QualityJudge(judge_client)
        metrics = _execute_suite(
            topics,
            repeats=repeats,
            max_sources=max_sources,
            settings=runtime_settings,
            evaluator=judge.evaluate,
            progress=progress,
        )
    return metrics, topics


def write_offline_benchmark_outputs(
    metrics: list[BenchmarkMetrics],
    topics: Sequence[OfflineTopic],
    *,
    output_dir: Path,
    settings: Settings,
    max_sources: int,
) -> tuple[Path, Path, Path, Path]:
    """Ghi benchmark artifacts và offline retrieval manifest."""

    raw_path, summary_path, report_path = write_benchmark_outputs(
        metrics,
        output_dir=output_dir,
        settings=settings,
    )
    retrieval_manifest_path = output_dir / "retrieval_manifest.json"
    retrieval_manifest = _retrieval_manifest(topics, max_sources=max_sources)
    retrieval_manifest_path.write_text(
        json.dumps(retrieval_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "# Báo cáo Benchmark Online",
        "# Báo cáo Benchmark Offline có Kiểm soát",
        1,
    )
    report = report.replace(
        "- Search provider: Tavily thông qua `SearchClient` của repo.",
        "- Retrieval provider: subset corpus offline do lab cung cấp; các kiến trúc nghiên cứu "
        "không gọi Tavily hoặc live web retrieval.",
        1,
    )
    topic_summary = ", ".join(topic.benchmark_metadata.topic_id for topic in topics)
    versions = sorted({topic.benchmark_metadata.benchmark_version for topic in topics})
    corpus_section = (
        "## Thiết lập Corpus Offline\n\n"
        f"- Topic được chọn: `{topic_summary}`.\n"
        f"- Phiên bản corpus: `{', '.join(versions)}`.\n"
        f"- Evidence dùng cho citation lấy từ `knowledge_base.source_documents` của từng topic.\n"
        f"- Retrieval dùng lexical ranking deterministic với `max_sources={max_sources}`.\n"
        "- Synthetic document luôn giữ nhãn rõ trong metadata và prompt evidence.\n"
        "- URL `https://offline.local/...` là benchmark locator ổn định, "
        "không phải live web page.\n"
        "- LLM provider và LangSmith tracing vẫn có thể online; chỉ research "
        "retrieval là offline và cố định.\n\n"
    )
    report = report.replace("## Phương pháp\n", corpus_section + "## Phương pháp\n", 1)
    report_path.write_text(report, encoding="utf-8")
    return raw_path, summary_path, report_path, retrieval_manifest_path


def _execute_suite(
    topics: Sequence[OfflineTopic],
    *,
    repeats: int,
    max_sources: int,
    settings: Settings,
    evaluator: Evaluator,
    progress: Progress | None,
) -> list[BenchmarkMetrics]:
    variant_settings = _variant_settings(settings)
    metrics: list[BenchmarkMetrics] = []
    total_runs = len(topics) * repeats * len(_VARIANTS)
    completed_runs = 0

    for repeat in range(1, repeats + 1):
        offset = (repeat - 1) % len(_VARIANTS)
        variant_order = _VARIANTS[offset:] + _VARIANTS[:offset]
        for topic in topics:
            case = topic.to_case(max_sources=max_sources)
            for run_name in variant_order:
                completed_runs += 1
                search_client = OfflineCorpusSearchClient(topic)
                runner = _runner_for(
                    run_name,
                    settings=variant_settings[run_name],
                    search_client=search_client,
                )
                if progress is not None:
                    progress(
                        f"[{completed_runs}/{total_runs}] {case.case_id} | "
                        f"{run_name} | repeat {repeat}"
                    )
                _, run_metrics = run_benchmark(
                    run_name,
                    case,
                    runner,
                    repeat=repeat,
                    evaluator=evaluator,
                )
                metrics.append(run_metrics)
                if progress is not None:
                    quality = (
                        "n/a"
                        if run_metrics.quality_score is None
                        else f"{run_metrics.quality_score:.1f}/10"
                    )
                    progress(
                        f"    status={run_metrics.status.value} "
                        f"latency={run_metrics.latency_seconds:.2f}s "
                        f"quality={quality} tokens={run_metrics.total_tokens}"
                    )
    return metrics


def _variant_settings(settings: Settings) -> dict[str, Settings]:
    return {
        BASELINE: settings.model_copy(update={"enable_critic": False}),
        MULTI_AGENT: settings.model_copy(update={"enable_critic": False}),
        MULTI_AGENT_CRITIC: settings.model_copy(update={"enable_critic": True, "max_revisions": 1}),
    }


def _runner_for(
    run_name: str,
    *,
    settings: Settings,
    search_client: OfflineCorpusSearchClient,
) -> Runner:
    if run_name == BASELINE:
        return lambda request: run_baseline(
            request,
            settings=settings,
            search_client=search_client,
        )
    if run_name in {MULTI_AGENT, MULTI_AGENT_CRITIC}:
        return lambda request: run_multi_agent(
            request,
            settings=settings,
            search_client=search_client,
        )
    raise ValueError(f"Unknown benchmark variant: {run_name}")


def _retrieval_manifest(
    topics: Sequence[OfflineTopic],
    *,
    max_sources: int,
) -> dict[str, object]:
    topic_entries: list[dict[str, object]] = []
    for topic in topics:
        case = topic.to_case(max_sources=max_sources)
        client = OfflineCorpusSearchClient(topic)
        topic_entries.append(
            {
                "topic_id": topic.benchmark_metadata.topic_id,
                "topic_name": topic.topic.name,
                "corpus_version": topic.benchmark_metadata.benchmark_version,
                "query": case.query,
                "audience": case.audience,
                "max_sources": case.max_sources,
                "selected_sources": client.selected_source_metadata(
                    case.query,
                    max_results=case.max_sources,
                ),
            }
        )
    return {
        "benchmark_mode": "offline-controlled-retrieval",
        "retrieval_provider": "OfflineCorpusSearchClient",
        "topics": topic_entries,
    }


def main() -> None:
    """Run the selected offline benchmark and write reproducible artifacts."""

    parser = argparse.ArgumentParser(description="Run the Lab 20 offline controlled benchmark")
    parser.add_argument(
        "--topic",
        default=None,
        help="Run one topic ID, for example AIAGENT-01 (smoke mode)",
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        default=None,
        help="Topic IDs to run; defaults to AIAGENT-01 AIAGENT-12 AIAGENT-22",
    )
    parser.add_argument("--repeats", type=int, default=2, help="Repeats per topic/variant")
    parser.add_argument("--max-sources", type=int, default=5, help="Offline sources per run")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("data/offline_benchmark"),
        help="Selected offline corpus directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/offline_benchmark"),
        help="Directory for offline benchmark outputs",
    )
    args = parser.parse_args()

    if args.topic is not None and args.topics is not None:
        parser.error("use either --topic or --topics, not both")
    selected_topics = (
        (args.topic,)
        if args.topic is not None
        else tuple(args.topics)
        if args.topics is not None
        else DEFAULT_OFFLINE_TOPICS
    )

    settings = get_settings()
    metrics, topics = run_offline_benchmark_suite(
        selected_topics,
        corpus_dir=args.corpus_dir,
        repeats=args.repeats,
        max_sources=args.max_sources,
        settings=settings,
        progress=print,
    )
    paths = write_offline_benchmark_outputs(
        metrics,
        topics,
        output_dir=args.output_dir,
        settings=settings,
        max_sources=args.max_sources,
    )
    print("\nOffline benchmark outputs:")
    for path in paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()
