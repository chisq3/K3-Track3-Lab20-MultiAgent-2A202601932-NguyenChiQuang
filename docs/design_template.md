# Thiết kế Hệ thống Nghiên cứu Multi-Agent

## 1. Bài toán

Hệ thống nhận một câu hỏi nghiên cứu kỹ thuật, tìm tối đa số nguồn người dùng yêu cầu, đánh giá evidence và tổng hợp câu trả lời có citation. Repo triển khai ba variant để benchmark trên cùng input:

1. **Baseline** — một agent thực hiện search + tổng hợp trong một lượt LLM.
2. **Multi-agent core** — Supervisor điều phối Researcher, Analyst và Writer.
3. **Multi-agent + Critic** — thêm Critic review với tối đa một vòng sửa.

Mục tiêu không phải chứng minh multi-agent luôn tốt hơn, mà đo trade-off giữa **quality, citation compliance, latency, token, cost và reliability**.

## 2. Phạm vi

- Query dạng nghiên cứu, tổng hợp hoặc so sánh chủ đề kỹ thuật.
- Online retrieval dùng Tavily và chuẩn hóa về `SourceDocument`.
- Controlled offline retrieval dùng 3 topic corpus cố định do lab cung cấp.
- Model chính: `openai/gpt-4o-mini` qua OpenRouter.
- Output: câu trả lời văn bản phù hợp `ResearchQuery.audience`.
- Citation chỉ được trỏ tới nguồn thực sự có trong shared state.
- PDF crawling toàn web và long-term memory nằm ngoài phạm vi core.

## 3. Quyết định công nghệ

| Hạng mục | Lựa chọn | Lý do |
|---|---|---|
| LLM | OpenRouter + `openai/gpt-4o-mini` | Chi phí thấp, hỗ trợ structured output tốt |
| Online search | Tavily | Trả title, URL và content có cấu trúc |
| Offline retrieval | `OfflineCorpusSearchClient` | Fixed evidence, deterministic lexical ranking |
| Routing | Deterministic Supervisor | Dễ test, không tốn thêm LLM call để route |
| Workflow | LangGraph | State handoff và conditional routing rõ ràng |
| Tracing | LangSmith | Phù hợp LangGraph và có cây span trực quan |
| Validation | Pydantic | Typed input/output nhất quán |
| Retry | Tenacity | Retry/backoff tập trung |
| Tests | Pytest + deterministic mocks | Không tốn API credit, không phụ thuộc mạng |

## 4. Vai trò agent

| Agent | Trách nhiệm | Input chính | Output chính | Failure mode đáng chú ý |
|---|---|---|---|---|
| Supervisor | Chọn bước tiếp theo và enforce guardrail | Shared state, iteration, errors | `next_route`, status, route history | route loop, timeout |
| Researcher | Tìm/lọc nguồn và tạo research notes | Query, `max_sources` | `sources`, `research_notes` | search timeout, nguồn yếu/trùng |
| Analyst | So sánh evidence, trích claim và chỉ ra gap | Sources + research notes | `analysis_notes` | suy diễn quá evidence |
| Writer | Viết final answer và citation | Query + sources + notes | `final_answer` | citation/source contract sai |
| Critic | Review claim/citation và quyết định pass/revise | Final answer + existing evidence | structured feedback | invalid revise feedback, extra failure surface |

Critic không có search client và không được thu thập evidence mới.

## 5. Shared state

`ResearchState` là single source of truth cho toàn workflow.

| Field | Trạng thái | Ý nghĩa |
|---|---|---|
| `request` | Implemented | Query, audience, source limit |
| `iteration` | Implemented | Đếm quyết định route |
| `route_history` | Implemented | Audit handoff |
| `sources` | Implemented | Nguồn đã chuẩn hóa |
| `research_notes` | Implemented | Output Researcher |
| `analysis_notes` | Implemented | Output Analyst |
| `final_answer` | Implemented | Output cuối |
| `agent_results` | Implemented | Structured agent outputs |
| `trace` | Implemented | Trace local/fallback |
| `errors` | Implemented | Error có thể quan sát |
| `next_route` | Implemented | Conditional route |
| `status` | Implemented | running/completed/partial/failed |
| `usage` | Implemented | Token/cost/search/LLM calls |
| `step_durations_seconds` | Implemented | Latency theo bước |
| `agent_attempts` | Implemented | Attempt theo worker |
| `retry_count` | Implemented | Tổng retry |
| `last_failed_agent` | Implemented | Failure context |
| `fallback_used` | Implemented | Có dùng fallback hay không |
| `stop_reason` | Implemented | Lý do dừng |
| `revision_count` | Implemented (bonus) | Giới hạn revision |
| `critic_result` / `critic_history` | Implemented (bonus) | Critic feedback |
| `trace_id` / `trace_url` | Implemented | Liên kết LangSmith |

## 6. Chính sách định tuyến

### Core

```text
START → supervisor

supervisor:
  timeout vượt budget                         → END
  iteration vượt max_iterations               → END
  worker lỗi và còn retry                      → retry worker
  analyst lỗi sau retry                        → writer fallback
  researcher/writer lỗi sau retry              → END failed
  thiếu sources hoặc research_notes            → researcher
  thiếu analysis_notes                         → analyst
  thiếu final_answer                           → writer
  final_answer tồn tại, critic OFF              → END completed

researcher → supervisor
analyst    → supervisor
writer     → supervisor
```

### Bonus Critic

```text
final_answer tồn tại, critic ON → critic
critic pass                     → END
critic revise, revision_count=0 → writer revision
critic tiếp tục revise hoặc lỗi → END partial/failed theo guardrail
```

## 7. Guardrails

| Guardrail | Chính sách |
|---|---|
| Max iterations | Core budget 6 route decisions; Critic mode có effective budget bổ sung |
| Workflow timeout | 60 giây mặc định, cấu hình bằng `TIMEOUT_SECONDS` |
| Provider timeout | Giới hạn theo LLM/search call |
| Retry | Có giới hạn + exponential backoff |
| Route validation | Chỉ route thuộc enum hợp lệ |
| Input validation | Query đủ dài; `max_sources` trong khoảng cho phép |
| Source validation | Loại source rỗng/trùng/thiếu dữ liệu bắt buộc |
| Citation validation | Citation ID/URL phải thuộc source set |
| Analyst fallback | Writer có thể dùng research notes sau analyst failure |
| Critic revision | `MAX_REVISIONS=1`, không re-search |
| Tracing | Fail-open, không làm workflow crash |

## 8. Kế hoạch đánh giá đã thực hiện

### Benchmark online

3 query:

1. `Research GraphRAG state-of-the-art and write a 500-word summary`
2. `Compare single-agent and multi-agent workflows for customer support`
3. `Summarize production guardrails for LLM agents`

Mỗi query chạy 3 repeats cho 3 variant → **27 runs**.

### Benchmark offline có kiểm soát

3 corpus topic:

1. `AIAGENT-01` — Single vs Multi-Agent.
2. `AIAGENT-12` — Critic and Verifier Agents.
3. `AIAGENT-22` — Cost, Latency and Parallelism.

Mỗi topic chạy 2 repeats cho 3 variant → **18 runs**.

Retrieval evidence được cố định và deterministic.

## 9. Metric

| Metric | Cách đo | Cách diễn giải |
|---|---|---|
| Latency | Wall-clock seconds | Orchestration overhead |
| Token usage | Provider input/output usage | Mức tiêu thụ context/generation |
| Cost | Provider-reported OpenRouter cost | Chi phí thực tế của architecture run |
| Quality | Blind judge 0–10 | Chỉ dùng cùng các metric khác vì có ceiling effect |
| Citation coverage | Sentence-level proxy có `[n]` | Proxy, không phải semantic fact coverage tuyệt đối |
| Citation validity | Strict ID/URL match với source set | Kiểm tra compliance citation |
| Success/failure | Final status | Reliability end-to-end |
| Iterations/retries | State metrics | Complexity/failure recovery |
| Revisions | Critic path | Giá trị/overhead của bonus loop |

Metric bổ sung dùng cho final interpretation:

```text
Valid completed rate
= completed AND strict citation_valid
```

## 10. Kết quả cuối

### Online

- Baseline: 100% completion; valid-completed 66.7%; 17.35s; 2,205 tokens; $0.000651/run.
- Multi-agent core: 77.8% completion; **valid-completed 77.8%**; 43.09s; 9,028 tokens; $0.002083/run.
- Multi-agent + Critic: 55.6% completion; valid-completed 55.6%; 45.49s; 14,085 tokens; $0.002873/run.

### Offline có kiểm soát

- Baseline: 100% completion; valid-completed 33.3%; 13.93s; 3,228 tokens; $0.000800/run.
- Multi-agent core: 66.7% completion; **valid-completed 66.7%**; 39.12s; 13,376 tokens; $0.002657/run.
- Multi-agent + Critic: 33.3% completion; valid-completed 33.3%; 46.03s; 18,446 tokens; $0.003067/run.

## 11. Kết luận thiết kế

1. **Baseline** nên là default cho task đơn giản hoặc khi latency/cost/completion reliability là ưu tiên chính.
2. **Core multi-agent** hợp lý khi strict citation compliance và auditability quan trọng; nó đạt valid-completed rate tốt nhất trong cả online và controlled offline benchmark.
3. **Critic** nên giữ optional: bounded loop hoạt động, nhưng benchmark chưa cho thấy quality gain đủ ổn định để bù token/cost và failure surface tăng thêm.
4. Không nên kết luận multi-agent “tốt hơn” chỉ bằng quality score; cần đọc cùng completion, citation validity, cost và failure behavior.

## 12. Definition of Done

- [x] Baseline và multi-agent dùng cùng model/query/source limit trong benchmark.
- [x] Shared state/handoff rõ ràng.
- [x] Retry, timeout, validation và fallback có test.
- [x] LangSmith trace evidence end-to-end.
- [x] Benchmark online 27 runs + failure analysis.
- [x] Controlled offline benchmark 18 runs.
- [x] Critic bounded revision loop.
- [x] Showcase static + Streamlit.
- [x] Ruff, mypy và pytest là quality gate trước khi nộp.
