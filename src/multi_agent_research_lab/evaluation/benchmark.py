"""Reproducible benchmark runner for baseline, multi-agent, and Critic variants."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter

from multi_agent_research_lab.agents.protocols import LLMCompletionClient
from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import (
    BenchmarkCase,
    BenchmarkMetrics,
    ResearchQuery,
    RunStatus,
)
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.evaluator import EvaluationOutcome, QualityJudge
from multi_agent_research_lab.runners import run_baseline, run_multi_agent
from multi_agent_research_lab.services.llm_client import LLMClient

Runner = Callable[[ResearchQuery], ResearchState]
Evaluator = Callable[[ResearchState], EvaluationOutcome]
Progress = Callable[[str], None]

BASELINE = "baseline"
MULTI_AGENT = "multi-agent"
MULTI_AGENT_CRITIC = "multi-agent-critic"
_VARIANTS = (BASELINE, MULTI_AGENT, MULTI_AGENT_CRITIC)

DEFAULT_BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        case_id="graphrag",
        query="Research GraphRAG state-of-the-art and write a 500-word summary",
        audience="technical learners",
        max_sources=5,
    ),
    BenchmarkCase(
        case_id="customer-support",
        query="Compare single-agent and multi-agent workflows for customer support",
        audience="technical learners",
        max_sources=5,
    ),
    BenchmarkCase(
        case_id="production-guardrails",
        query="Summarize production guardrails for LLM agents",
        audience="technical learners",
        max_sources=5,
    ),
)


def run_benchmark(
    run_name: str,
    case: BenchmarkCase,
    runner: Runner,
    *,
    repeat: int = 1,
    evaluator: Evaluator | None = None,
) -> tuple[ResearchState, BenchmarkMetrics]:
    """Execute one benchmark run and capture failure instead of aborting the suite."""

    request = case.to_request()
    started = perf_counter()
    try:
        state = runner(request)
    except Exception as exc:  # benchmark must record provider/runtime failures
        state = ResearchState(
            request=request,
            status=RunStatus.FAILED,
            stop_reason="runner_exception",
            errors=[f"{type(exc).__name__}: {exc}"],
        )
    latency = perf_counter() - started

    evaluation: EvaluationOutcome | None = None
    evaluation_error: str | None = None
    if evaluator is not None and state.final_answer and state.sources:
        try:
            evaluation = evaluator(state)
        except Exception as exc:  # evaluation failure must not erase system metrics
            evaluation_error = f"judge_error={type(exc).__name__}: {exc}"

    metrics = _metrics_from_state(
        run_name=run_name,
        case=case,
        repeat=repeat,
        state=state,
        latency_seconds=latency,
        evaluation=evaluation,
        evaluation_error=evaluation_error,
    )
    return state, metrics


def run_benchmark_suite(
    cases: Sequence[BenchmarkCase] = DEFAULT_BENCHMARK_CASES,
    *,
    repeats: int = 2,
    settings: Settings | None = None,
    judge_llm_client: LLMCompletionClient | None = None,
    progress: Progress | None = None,
) -> list[BenchmarkMetrics]:
    """Run all three architectures with interleaved ordering for fairer latency comparison."""

    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if not cases:
        raise ValueError("benchmark requires at least one case")

    runtime_settings = settings or get_settings()
    variant_settings = {
        BASELINE: runtime_settings.model_copy(update={"enable_critic": False}),
        MULTI_AGENT: runtime_settings.model_copy(update={"enable_critic": False}),
        MULTI_AGENT_CRITIC: runtime_settings.model_copy(
            update={"enable_critic": True, "max_revisions": 1}
        ),
    }
    runners: dict[str, Runner] = {
        BASELINE: lambda request: run_baseline(
            request,
            settings=variant_settings[BASELINE],
        ),
        MULTI_AGENT: lambda request: run_multi_agent(
            request,
            settings=variant_settings[MULTI_AGENT],
        ),
        MULTI_AGENT_CRITIC: lambda request: run_multi_agent(
            request,
            settings=variant_settings[MULTI_AGENT_CRITIC],
        ),
    }

    if judge_llm_client is not None:
        judge = QualityJudge(judge_llm_client)
        return _execute_suite(cases, repeats, runners, judge.evaluate, progress)

    with LLMClient(runtime_settings) as judge_client:
        judge = QualityJudge(judge_client)
        return _execute_suite(cases, repeats, runners, judge.evaluate, progress)


def _execute_suite(
    cases: Sequence[BenchmarkCase],
    repeats: int,
    runners: dict[str, Runner],
    evaluator: Evaluator,
    progress: Progress | None,
) -> list[BenchmarkMetrics]:
    metrics: list[BenchmarkMetrics] = []
    total_runs = len(cases) * repeats * len(_VARIANTS)
    completed_runs = 0

    for repeat in range(1, repeats + 1):
        offset = (repeat - 1) % len(_VARIANTS)
        variant_order = _VARIANTS[offset:] + _VARIANTS[:offset]
        for case in cases:
            for run_name in variant_order:
                completed_runs += 1
                if progress is not None:
                    progress(
                        f"[{completed_runs}/{total_runs}] {case.case_id} | "
                        f"{run_name} | repeat {repeat}"
                    )
                _, run_metrics = run_benchmark(
                    run_name,
                    case,
                    runners[run_name],
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


def _metrics_from_state(
    *,
    run_name: str,
    case: BenchmarkCase,
    repeat: int,
    state: ResearchState,
    latency_seconds: float,
    evaluation: EvaluationOutcome | None,
    evaluation_error: str | None,
) -> BenchmarkMetrics:
    from multi_agent_research_lab.evaluation.evaluator import (
        citation_coverage,
        citation_validation_error,
        citation_validity,
    )

    quality_score = evaluation.evaluation.total_score if evaluation is not None else None
    answer = state.final_answer or ""
    latest_critic = state.critic_history[-1] if state.critic_history else None
    note_parts = [message for message in state.errors if message]
    if evaluation_error:
        note_parts.append(evaluation_error)
    citation_error = citation_validation_error(state) if answer else None
    if citation_error is not None:
        note_parts.append(f"citation_invalid={citation_error}")
    notes = "; ".join(note_parts)

    return BenchmarkMetrics(
        run_name=run_name,
        query_id=case.case_id,
        query=case.query,
        audience=case.audience,
        max_sources=case.max_sources,
        repeat=repeat,
        status=state.status,
        stop_reason=("completed" if state.status is RunStatus.COMPLETED else state.stop_reason),
        latency_seconds=latency_seconds,
        input_tokens=state.usage.input_tokens,
        output_tokens=state.usage.output_tokens,
        total_tokens=state.usage.total_tokens,
        estimated_cost_usd=(state.usage.estimated_cost_usd if state.usage.cost_complete else None),
        cost_complete=state.usage.cost_complete,
        search_calls=state.usage.search_calls,
        llm_calls=state.usage.llm_calls,
        iterations=state.iteration,
        retry_count=state.retry_count,
        fallback_used=state.fallback_used,
        quality_score=quality_score,
        citation_coverage=citation_coverage(answer) if answer else None,
        citation_validity=citation_validity(state) if answer else None,
        failure_rate=0.0 if state.status is RunStatus.COMPLETED else 1.0,
        critic_decision=latest_critic.decision if latest_critic is not None else None,
        critic_quality_score=(latest_critic.quality_score if latest_critic is not None else None),
        revision_count=state.revision_count,
        judge_input_tokens=(evaluation.input_tokens or 0) if evaluation is not None else 0,
        judge_output_tokens=(evaluation.output_tokens or 0) if evaluation is not None else 0,
        judge_cost_usd=evaluation.cost_usd if evaluation is not None else None,
        trace_id=state.trace_id,
        trace_url=state.trace_url,
        notes=notes,
    )


def main() -> None:
    """Run the official benchmark and write raw, summary, and Markdown artefacts."""

    parser = argparse.ArgumentParser(description="Run the Lab 20 benchmark suite")
    parser.add_argument("--repeats", type=int, default=2, help="Repeats per case/variant")
    parser.add_argument(
        "--case",
        choices=[case.case_id for case in DEFAULT_BENCHMARK_CASES],
        default=None,
        help="Run only one named case for a smoke benchmark",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Directory for benchmark outputs",
    )
    args = parser.parse_args()

    settings = get_settings()
    selected_cases = (
        DEFAULT_BENCHMARK_CASES
        if args.case is None
        else tuple(case for case in DEFAULT_BENCHMARK_CASES if case.case_id == args.case)
    )
    metrics = run_benchmark_suite(
        selected_cases,
        repeats=args.repeats,
        settings=settings,
        progress=print,
    )

    from multi_agent_research_lab.evaluation.report import write_benchmark_outputs

    paths = write_benchmark_outputs(
        metrics,
        output_dir=args.output_dir,
        settings=settings,
    )
    print("\nBenchmark outputs:")
    for path in paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()
