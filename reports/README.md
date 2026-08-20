# Artifact Đánh giá Cuối

Thư mục `reports/` chỉ giữ **evidence cuối** của bài. Smoke/pilot output là artifact phát triển và không nên commit vào bản nộp.

## 1. Benchmark online chính thức

Các file ở root `reports/` là benchmark online chính:

- `benchmark_raw.jsonl` — 27 raw architecture runs.
- `benchmark_summary.csv` — số liệu aggregate về latency, token, cost, quality, citation và reliability.
- `benchmark_report.md` — báo cáo chính thức.
- `trace_evidence.md` — trace và failure-mode evidence.
- `images/langsmith_multi_agent_trace.png` — screenshot cây LangSmith trace.

Quy mô: **3 queries × 3 architectures × 3 repeats = 27 runs**.

Thí nghiệm này giữ nguyên các yếu tố thực tế như Tavily retrieval, OpenRouter/provider latency, timeout và retry.

## 2. Benchmark offline có kiểm soát

`offline_benchmark/` chứa thí nghiệm phụ trợ dùng fixed corpus:

- `benchmark_raw.jsonl`
- `benchmark_summary.csv`
- `benchmark_report.md`
- `retrieval_manifest.json`

Quy mô: **3 corpus topics × 3 architectures × 2 repeats = 18 runs**.

Retrieval evidence là deterministic và cố định, vì vậy có thể so sánh kiến trúc mà không bị Tavily search variance chi phối.

## 3. Quy tắc diễn giải

Không gộp 27 online runs và 18 offline runs thành một average chung.

- **Online:** đo hành vi end-to-end gần production hơn.
- **Offline:** đo architecture behavior dưới cùng một evidence set.

Ngoài các average, cần xem thêm metric tổng hợp:

```text
Valid completed rate
= status == completed AND citation_validity == 1
```

Kết quả cuối:

| Kiến trúc | Online | Offline có kiểm soát |
|---|---:|---:|
| Baseline | 66.7% | 33.3% |
| Multi-agent core | **77.8%** | **66.7%** |
| Multi-agent + Critic | 55.6% | 33.3% |

Quality/citation-validity average chỉ được tính trên output có thể chấm, nên cần chú ý survivorship bias và ceiling effect của judge 0–10.
