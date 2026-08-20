# Hướng dẫn Lab 20: Hệ thống Nghiên cứu Multi-Agent

## Bối cảnh

Bài lab xây dựng một research assistant có thể nhận câu hỏi nghiên cứu, tìm nguồn, phân tích và viết câu trả lời cuối. Hai kiến trúc được triển khai trên cùng input để so sánh:

1. **Single-agent baseline** — một agent thực hiện search + tổng hợp trong một lượt generation.
2. **Multi-agent workflow** — Supervisor điều phối Researcher, Analyst và Writer; Critic là bonus tùy chọn.

Bản repo hiện tại đã hoàn thành toàn bộ core workflow, tracing, benchmark và bonus Critic.

## Quy tắc thiết kế

- Chỉ thêm agent khi vai trò tạo ra trách nhiệm rõ ràng.
- Shared state là nguồn dữ liệu duy nhất cho handoff và debug.
- Supervisor định tuyến deterministic, không dùng LLM để route.
- Có max iterations, timeout, retry/fallback và validation.
- Citation chỉ được trỏ tới source thực sự tồn tại trong state.
- Benchmark bằng số liệu; không kết luận chỉ dựa trên một output đẹp.
- Critic không được search lại và chỉ có tối đa một revision.

## Trạng thái milestone

### Milestone 1 — Baseline ✅

- OpenRouter LLM client hoàn chỉnh.
- Tavily search client hoàn chỉnh.
- Baseline chạy end-to-end, thu latency/token/cost và trace.

### Milestone 2 — Supervisor & LangGraph ✅

- Routing deterministic qua `Researcher → Analyst → Writer`.
- Có stop condition, timeout và max iteration.
- Có retry/fallback theo failure context.

### Milestone 3 — Worker agents ✅

- Researcher tìm/chuẩn hóa nguồn và tạo `research_notes`.
- Analyst đánh giá evidence và tạo `analysis_notes`.
- Writer tổng hợp final answer có citation validation.

### Milestone 4 — Trace & Benchmark ✅

- LangSmith tracing end-to-end.
- Benchmark online 27 runs.
- Controlled offline benchmark 18 runs.
- Independent blind quality judge, citation coverage/validity, latency, token, cost và failure rate.

### Milestone 5 — Critic bonus ✅

- `ENABLE_CRITIC=false` mặc định.
- Critic trả structured `pass/revise` feedback.
- Writer revision dùng existing sources/analysis, không re-search.
- `MAX_REVISIONS=1` ngăn revision loop vô hạn.

## Failure mode quan sát được

Final benchmark ghi nhận ba nhóm lỗi thực tế:

1. **Timeout:** workflow nhiều bước tăng execution surface và dễ chạm timeout hơn baseline.
2. **Writer citation validation:** Writer có thể tạo Sources section không đúng citation contract; guardrail retry rồi dừng nếu vẫn sai.
3. **Critic structured-output validation:** Critic có thể chọn `revise` nhưng không cung cấp issue actionable; validator từ chối output và không cho loop vô hạn.

Các failure này được giữ trong report thay vì lọc bỏ để success rate phản ánh đúng hành vi hệ thống.

## Troubleshooting

### macOS: `SSLCertVerificationError`

Nếu Python cài từ python.org không tìm thấy CA bundle, có thể chọn một trong các cách:

```bash
/Applications/Python\ 3.12/Install\ Certificates.command
```

hoặc dùng `certifi`, hoặc đặt:

```bash
export SSL_CERT_FILE=$(python -m certifi)
```

Đây là lỗi môi trường, không nhất thiết do API key.

## Exit Ticket — Câu trả lời

### 1. Khi nào nên dùng multi-agent? Vì sao?

Nên dùng multi-agent cho research task cần **strict citation compliance, auditability, artefact trung gian và validation/retry rõ ràng**, đặc biệt khi chi phí của một final answer không hợp lệ cao hơn orchestration overhead.

Trong benchmark online, core multi-agent tạo **7/9 = 77.8%** runs vừa `completed` vừa strict citation-valid, cao hơn baseline **6/9 = 66.7%**. Trong controlled offline benchmark, core multi-agent đạt **4/6 = 66.7%**, trong khi baseline chỉ **2/6 = 33.3%**. Kết quả offline đặc biệt quan trọng vì evidence set được cố định, cho thấy lợi thế citation compliance không chỉ là hệ quả của Tavily variance.

### 2. Khi nào không nên dùng multi-agent? Vì sao?

Không nên dùng multi-agent cho tác vụ đơn giản hoặc khi **latency, cost và completion reliability** quan trọng hơn khả năng orchestration/validation.

Trong benchmark online, baseline hoàn thành **100%** runs với trung bình **17.35s**, **2,205 tokens** và **$0.000651/run**. Core multi-agent hoàn thành **77.8%** runs với **43.09s**, **9,028 tokens** và **$0.002083/run**. Vì vậy multi-agent chỉ đáng dùng khi lợi ích về citation/auditability đủ quan trọng để bù overhead.

Critic nên giữ là optional bonus mode: benchmark cho thấy nó tăng token/cost và failure surface nhưng chưa tạo quality gain ổn định.
