# Corpus Benchmark Offline được Chọn

Thư mục này chứa **subset 3 topic** được chọn từ `AI Agent Offline Research Corpus Benchmark v2` do chủ Lab 20 cung cấp.

Các topic sử dụng:

- `AIAGENT-01` — Single-Agent vs Multi-Agent Architectures for Complex Research Tasks.
- `AIAGENT-12` — Critic and Verifier Agents for Research Report Quality.
- `AIAGENT-22` — Cost, Latency, and Parallelism in Multi-Agent Research.

## Mục đích sử dụng trong repo

Corpus này không dùng để train model. Nó được dùng làm **controlled benchmark** để tất cả kiến trúc nhận cùng một tập evidence cố định, từ đó giảm biến thiên do Tavily search và làm phép so sánh dễ tái lập hơn.

Offline benchmark chỉ dùng `knowledge_base.source_documents` của mỗi topic làm nguồn retrieval có thể citation. `OfflineCorpusSearchClient` thực hiện lexical ranking deterministic và **không gọi Tavily, không mở provenance URL**.

OpenRouter vẫn được dùng cho generation/judge và LangSmith có thể vẫn online; chữ “offline” ở đây chỉ nói về **research retrieval cố định**.

## Synthetic evidence

Các tài liệu synthetic giữ nguyên metadata `is_synthetic=true` và được gắn nhãn rõ khi đưa vào prompt. URL dạng:

```text
https://offline.local/...
```

chỉ là benchmark locator ổn định để citation validator hiện tại hoạt động; đây không phải website thật.

## Quan hệ với benchmark online

- `reports/benchmark_report.md`: benchmark online thực tế, 27 runs, có Tavily/network/provider variance.
- `reports/offline_benchmark/benchmark_report.md`: controlled offline benchmark, 18 runs, evidence cố định.

Không cộng 45 runs thành một average chung vì hai thí nghiệm trả lời hai câu hỏi khác nhau.

## Ghi chú quyền phân phối

Corpus được chủ Lab 20 cung cấp cho mục đích coursework. ZIP gốc không có standalone redistribution license. Nếu repo được public, chỉ giữ subset này khi phạm vi sử dụng đã được chủ lab cho phép hoặc bổ sung NOTICE/license phù hợp.
