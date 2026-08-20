"""Showcase Streamlit cho hệ thống nghiên cứu Multi-Agent của Lab 20.

Màn hình mặc định chỉ đọc benchmark artifact đã commit nên có thể trình bày mà không
gọi API. Live research là chế độ tùy chọn và dùng trực tiếp production runners.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import streamlit as st

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import LabError
from multi_agent_research_lab.core.schemas import ResearchQuery, RunStatus
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.offline_corpus import (
    OfflineCorpus,
    OfflineCorpusSearchClient,
)
from multi_agent_research_lab.runners import run_baseline, run_multi_agent

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
OFFLINE_REPORTS_DIR = REPORTS_DIR / "offline_benchmark"
CORPUS_DIR = ROOT / "data" / "offline_benchmark"
TRACE_IMAGE = REPORTS_DIR / "images" / "langsmith_multi_agent_trace.png"

VARIANT_LABELS = {
    "baseline": "Single-agent baseline",
    "multi-agent": "Multi-agent core",
    "multi-agent-critic": "Multi-agent + Critic",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            clean = line.strip()
            if not clean:
                continue
            try:
                value = json.loads(clean)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _pct(value: object) -> str:
    numeric = _as_float(value)
    return "n/a" if numeric is None else f"{numeric:.0%}"


def _number(value: object, digits: int = 2) -> str:
    numeric = _as_float(value)
    return "n/a" if numeric is None else f"{numeric:.{digits}f}"


def _cost(value: object) -> str:
    numeric = _as_float(value)
    return "n/a" if numeric is None else f"${numeric:.6f}"


def _valid_completed_rates(raw_rows: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, int] = {}
    valid_completed: dict[str, int] = {}
    for row in raw_rows:
        run_name = str(row.get("run_name", ""))
        if not run_name:
            continue
        totals[run_name] = totals.get(run_name, 0) + 1
        validity = _as_float(row.get("citation_validity"))
        if row.get("status") == RunStatus.COMPLETED.value and validity == 1.0:
            valid_completed[run_name] = valid_completed.get(run_name, 0) + 1
    return {
        name: valid_completed.get(name, 0) / total for name, total in totals.items() if total > 0
    }


def _trace_count(raw_rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in raw_rows if row.get("trace_url"))


def _summary_table(
    summary_rows: list[dict[str, str]],
    raw_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    valid_rates = _valid_completed_rates(raw_rows)
    result: list[dict[str, str]] = []
    for row in summary_rows:
        run_name = row.get("run_name", "")
        result.append(
            {
                "Kiến trúc": VARIANT_LABELS.get(run_name, run_name),
                "Số runs": row.get("runs", ""),
                "Thành công": _pct(row.get("success_rate")),
                "Valid completed": _pct(valid_rates.get(run_name)),
                "Latency": f"{_number(row.get('avg_latency_seconds'))} s",
                "Tokens": _number(row.get("avg_total_tokens"), 0),
                "Cost": _cost(row.get("avg_estimated_cost_usd")),
                "Quality*": _number(row.get("avg_quality_score")),
                "Citation coverage": _pct(row.get("avg_citation_coverage")),
                "Citation validity*": _pct(row.get("avg_citation_validity")),
            }
        )
    return result


def _best_valid_completed(raw_rows: list[dict[str, Any]]) -> tuple[str, float] | None:
    rates = _valid_completed_rates(raw_rows)
    if not rates:
        return None
    run_name, rate = max(rates.items(), key=lambda item: item[1])
    return VARIANT_LABELS.get(run_name, run_name), rate


def _status_message(state: ResearchState) -> None:
    if state.status is RunStatus.COMPLETED:
        st.success(f"Run hoàn thành · {state.stop_reason or 'completed'}")
    elif state.status is RunStatus.PARTIAL:
        st.warning(f"Run partial · {state.stop_reason or 'partial'}")
    else:
        st.error(f"Run {state.status.value} · {state.stop_reason or 'không có lý do dừng'}")


def _render_state(state: ResearchState, elapsed: float) -> None:
    _status_message(state)
    metric_cols = st.columns(6)
    metric_cols[0].metric("Latency", f"{elapsed:.2f}s")
    metric_cols[1].metric("Tokens", f"{state.usage.total_tokens:,}")
    metric_cols[2].metric(
        "Cost",
        _cost(state.usage.estimated_cost_usd) if state.usage.cost_complete else "n/a",
    )
    metric_cols[3].metric("Nguồn", len(state.sources))
    metric_cols[4].metric("Retry", state.retry_count)
    metric_cols[5].metric("Revision", state.revision_count)

    st.subheader("Câu trả lời cuối")
    if state.final_answer:
        st.markdown(state.final_answer)
    else:
        st.info("Run không tạo được final answer.")

    route = " → ".join(item.value for item in state.route_history) or "không có route được ghi"
    st.subheader("Luồng thực thi")
    st.code(route, language=None)
    st.caption(
        f"Iterations: {state.iteration} · Search calls: {state.usage.search_calls} · "
        f"LLM calls: {state.usage.llm_calls}"
    )

    if state.critic_history:
        latest = state.critic_history[-1]
        with st.expander("Đánh giá của Critic", expanded=True):
            st.write(
                {
                    "decision": latest.decision.value,
                    "quality_score": latest.quality_score,
                    "citation_coverage": latest.citation_coverage,
                    "reviews": len(state.critic_history),
                    "revisions": state.revision_count,
                }
            )
            if latest.issues:
                st.markdown("**Vấn đề**")
                st.write(latest.issues)
            if latest.citation_issues:
                st.markdown("**Vấn đề citation**")
                st.write(latest.citation_issues)
            if latest.unsupported_claims:
                st.markdown("**Claim thiếu evidence**")
                st.write(latest.unsupported_claims)
            if latest.revision_instructions:
                st.markdown("**Hướng dẫn sửa**")
                st.write(latest.revision_instructions)

    with st.expander(f"Nguồn ({len(state.sources)})"):
        for index, source in enumerate(state.sources, start=1):
            synthetic = source.metadata.get("is_synthetic") is True
            badge = " · evidence synthetic từ corpus" if synthetic else ""
            st.markdown(f"**[{index}] {source.title}**{badge}")
            if source.url:
                st.caption(source.url)
            preview = source.snippet.strip().replace("\n", " ")
            st.write(preview[:500] + ("…" if len(preview) > 500 else ""))

    if state.errors:
        with st.expander("Cảnh báo / lỗi", expanded=True):
            for error in state.errors:
                st.warning(error)

    if state.trace_url:
        st.markdown(f"[Mở run này trên LangSmith ↗]({state.trace_url})")
    elif state.trace_id:
        st.caption(f"LangSmith trace ID: {state.trace_id} (không có URL)")
    else:
        st.caption("Không có LangSmith trace hoặc tracing đang tắt.")


def _run_live(
    *,
    mode: str,
    architecture: str,
    max_sources: int,
    query: str,
    audience: str,
    topic_id: str | None,
) -> None:
    settings = get_settings()
    if not settings.openrouter_api_key:
        st.error("Cần `OPENROUTER_API_KEY` để chạy live generation.")
        return
    if mode == "Online · Tavily" and not settings.tavily_api_key:
        st.error("Cần `TAVILY_API_KEY` cho live retrieval online.")
        return

    critic_enabled = architecture == "multi-agent-critic"
    runtime_settings = settings.model_copy(
        update={"enable_critic": critic_enabled, "max_revisions": 1}
    )

    search_client: OfflineCorpusSearchClient | None = None
    if mode == "Offline · corpus cố định":
        if topic_id is None:
            st.error("Hãy chọn một offline topic trước.")
            return
        topic = OfflineCorpus(CORPUS_DIR).load_topic(topic_id)
        request = topic.to_case(max_sources=max_sources).to_request()
        search_client = OfflineCorpusSearchClient(topic)
    else:
        request = ResearchQuery(query=query, audience=audience, max_sources=max_sources)

    started = perf_counter()
    try:
        if architecture == "baseline":
            state = run_baseline(
                request,
                settings=runtime_settings,
                search_client=search_client,
            )
        else:
            state = run_multi_agent(
                request,
                settings=runtime_settings,
                search_client=search_client,
            )
    except LabError as exc:
        st.error(f"Live run thất bại: {exc}")
        return
    except Exception as exc:  # Streamlit should surface unexpected demo/runtime issues cleanly.
        st.exception(exc)
        return
    _render_state(state, perf_counter() - started)


def _render_overview() -> None:
    online_summary = _read_csv(REPORTS_DIR / "benchmark_summary.csv")
    online_raw = _read_jsonl(REPORTS_DIR / "benchmark_raw.jsonl")
    offline_summary = _read_csv(OFFLINE_REPORTS_DIR / "benchmark_summary.csv")
    offline_raw = _read_jsonl(OFFLINE_REPORTS_DIR / "benchmark_raw.jsonl")

    st.subheader("Tổng quan benchmark đã chốt")
    st.caption(
        "Trang này dùng để trình bày: chỉ đọc final artifacts trong `reports/` và không "
        "gọi LLM, Tavily hoặc LangSmith API."
    )

    top = st.columns(4)
    top[0].metric("Runs online", len(online_raw) or "—")
    top[1].metric("Runs offline", len(offline_raw) or "—")
    top[2].metric("Kiến trúc", 3)
    trace_total = _trace_count(online_raw)
    top[3].metric("Trace URL online", f"{trace_total}/{len(online_raw)}" if online_raw else "—")

    online_best = _best_valid_completed(online_raw)
    offline_best = _best_valid_completed(offline_raw)
    if online_best and offline_best:
        st.info(
            "**Kết quả chính:** baseline là mốc efficiency/reliability, trong khi "
            f"**{online_best[0]}** có strict citation-valid completed rate cao nhất "
            f"ở online ({online_best[1]:.0%}) và **{offline_best[0]}** dẫn đầu controlled "
            f"offline experiment ({offline_best[1]:.0%})."
        )

    online_tab, offline_tab = st.tabs(
        ["Online · retrieval thực tế", "Offline · retrieval có kiểm soát"]
    )
    with online_tab:
        if online_summary:
            st.dataframe(
                _summary_table(online_summary, online_raw),
                use_container_width=True,
            )
            st.caption(
                "Thí nghiệm chính 27 runs: 3 query × 3 kiến trúc × 3 repeats. "
                "Tavily/network/provider variance được giữ như một phần hành vi thực tế."
            )
            _download_artifacts(REPORTS_DIR, "online")
        else:
            st.warning("Không tìm thấy `reports/benchmark_summary.csv`.")

    with offline_tab:
        if offline_summary:
            st.dataframe(
                _summary_table(offline_summary, offline_raw),
                use_container_width=True,
            )
            st.caption(
                "Thí nghiệm phụ trợ 18 runs: 3 corpus topic × 3 kiến trúc × 2 repeats. "
                "Retrieval evidence cố định và deterministic; OpenRouter generation vẫn có "
                "thể biến thiên."
            )
            _download_artifacts(OFFLINE_REPORTS_DIR, "offline")
        else:
            st.warning("Không tìm thấy `reports/offline_benchmark/benchmark_summary.csv`.")

    st.caption(
        "* Average quality và citation validity chỉ tính trên output có thể chấm. "
        "Cột 'Valid completed' là end-to-end rate: completed VÀ strict citation-valid."
    )


def _download_artifacts(directory: Path, prefix: str) -> None:
    buttons = st.columns(2)
    report_path = directory / "benchmark_report.md"
    summary_path = directory / "benchmark_summary.csv"
    if report_path.is_file():
        buttons[0].download_button(
            "Tải báo cáo",
            report_path.read_bytes(),
            file_name=f"{prefix}_benchmark_report.md",
            mime="text/markdown",
            key=f"{prefix}-report",
        )
    if summary_path.is_file():
        buttons[1].download_button(
            "Tải summary CSV",
            summary_path.read_bytes(),
            file_name=f"{prefix}_benchmark_summary.csv",
            mime="text/csv",
            key=f"{prefix}-summary",
        )


def _render_live() -> None:
    st.subheader("Chạy nghiên cứu trực tiếp")
    st.caption(
        "Live mode gọi OpenRouter; online mode gọi thêm Tavily. Khi thuyết trình, nên dùng "
        "benchmark snapshot nếu cần kết quả ổn định không phụ thuộc network/provider."
    )

    left, right = st.columns([1, 1])
    with left:
        mode = st.radio("Chế độ retrieval", ["Offline · corpus cố định", "Online · Tavily"])
    with right:
        architecture = st.selectbox(
            "Kiến trúc",
            list(VARIANT_LABELS),
            format_func=lambda value: VARIANT_LABELS[value],
            index=1,
        )

    max_sources = st.slider("Số nguồn tối đa", min_value=1, max_value=10, value=5)
    topic_id: str | None = None
    audience = "technical learners"
    query = "Compare single-agent and multi-agent workflows for customer support"

    if mode == "Offline · corpus cố định":
        try:
            corpus = OfflineCorpus(CORPUS_DIR)
            topic_ids = list(corpus.available_topic_ids())
        except LabError as exc:
            st.error(f"Không thể đọc offline corpus: {exc}")
            return
        topic_id = st.selectbox("Topic corpus", topic_ids)
        topic = corpus.load_topic(topic_id)
        st.markdown(f"**Câu hỏi nghiên cứu:** {topic.topic.research_question}")
        st.caption(f"Đối tượng: {topic.topic.target_audience}")
    else:
        query = st.text_area("Câu hỏi nghiên cứu", value=query, height=100)
        audience = st.text_input("Đối tượng", value=audience)

    settings = get_settings()
    status_cols = st.columns(3)
    status_cols[0].metric("OpenRouter", "sẵn sàng" if settings.openrouter_api_key else "thiếu key")
    status_cols[1].metric(
        "Tavily",
        "không cần"
        if mode == "Offline · corpus cố định"
        else "sẵn sàng"
        if settings.tavily_api_key
        else "thiếu key",
    )
    status_cols[2].metric(
        "LangSmith",
        "đang bật" if settings.langsmith_tracing and settings.langsmith_api_key else "tùy chọn/tắt",
    )

    if st.button("Chạy nghiên cứu", type="primary", use_container_width=True):
        with st.spinner("Đang chạy kiến trúc đã chọn…"):
            _run_live(
                mode=mode,
                architecture=architecture,
                max_sources=max_sources,
                query=query,
                audience=audience,
                topic_id=topic_id,
            )


def _render_architecture() -> None:
    st.subheader("Kiến trúc & evidence")
    core, critic = st.columns(2)
    with core:
        st.markdown("**Luồng multi-agent core**")
        st.code(
            "Supervisor → Researcher → Supervisor → Analyst → Supervisor → Writer → Done",
            language=None,
        )
        st.caption("Chế độ mặc định: ENABLE_CRITIC=false")
    with critic:
        st.markdown("**Luồng Critic tùy chọn**")
        st.code(
            "Writer → Critic → pass | one bounded revise → Writer → Critic → stop",
            language=None,
        )
        st.caption("Bonus assurance mode: MAX_REVISIONS=1")

    online, offline = st.columns(2)
    with online:
        st.markdown("**Retrieval online**")
        st.write("Tavily → SourceDocument chuẩn hóa → cùng research agents")
    with offline:
        st.markdown("**Retrieval offline có kiểm soát**")
        st.write("Lab corpus JSON → deterministic lexical ranking → cùng research agents")

    st.markdown(
        "Demo import trực tiếp production runners. Demo **không duplicate** Supervisor, "
        "Researcher, Analyst, Writer, Critic, validation, retry hoặc tracing logic."
    )
    if TRACE_IMAGE.is_file():
        st.image(str(TRACE_IMAGE), caption="Evidence LangSmith multi-agent trace đã chụp")
    else:
        st.caption(
            "Không tìm thấy screenshot trace tại `reports/images/langsmith_multi_agent_trace.png`"
        )


def main() -> None:
    st.set_page_config(
        page_title="Lab 20 · Showcase Nghiên cứu Multi-Agent",
        page_icon="🧭",
        layout="wide",
    )
    st.markdown(
        """
        <style>
        .block-container {max-width: 1280px; padding-top: 2rem; padding-bottom: 3rem;}
        div[data-testid="stMetric"] {
            border: 1px solid rgba(120,120,120,.22);
            padding: .75rem;
            border-radius: .75rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("🧭 Hệ thống Nghiên cứu Multi-Agent")
    st.markdown(
        "**Showcase Lab 20:** so sánh single-agent baseline với multi-agent do Supervisor "
        "điều phối, có Critic tùy chọn, LangSmith tracing và đánh giá online + "
        "offline có kiểm soát."
    )

    overview, live, architecture = st.tabs(
        ["Tổng quan benchmark", "Chạy live", "Kiến trúc & trace"]
    )
    with overview:
        _render_overview()
    with live:
        _render_live()
    with architecture:
        _render_architecture()


if __name__ == "__main__":
    main()
