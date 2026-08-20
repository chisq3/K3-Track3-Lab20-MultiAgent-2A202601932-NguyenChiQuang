# Lab 20: Hệ thống Nghiên cứu Multi-Agent

Đây là bản triển khai hoàn chỉnh của **Lab 20 – Multi-Agent Systems**, dùng để so sánh một **single-agent baseline** với workflow nghiên cứu nhiều agent do **Supervisor** điều phối. Hệ thống triển khai các vai trò **Researcher → Analyst → Writer** và có thêm **Critic** ở chế độ bonus với vòng sửa bị giới hạn.

Repo tập trung vào một câu hỏi thực nghiệm: **khi nào multi-agent thực sự đáng dùng, và chi phí điều phối phải trả là bao nhiêu?** Vì vậy ngoài demo, project có tracing, guardrail, benchmark online thực tế và benchmark offline có kiểm soát.

## Kết quả chính

Hai thí nghiệm cuối được giữ tách biệt vì chúng đo hai khía cạnh khác nhau:

- **Benchmark online:** 27 runs = 3 query × 3 kiến trúc × 3 lần lặp, dùng Tavily + OpenRouter trong điều kiện mạng/provider thực tế.
- **Benchmark offline có kiểm soát:** 18 runs = 3 topic × 3 kiến trúc × 2 lần lặp, dùng corpus cố định do lab cung cấp để loại bỏ biến thiên của Tavily retrieval.

### Benchmark online – 27 runs

| Kiến trúc | Hoàn thành | Hoàn thành + citation hợp lệ | Latency TB | Tokens TB | Cost TB/run | Quality* |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | **100%** | 66.7% | **17.35s** | **2,205** | **$0.000651** | 10.00 |
| Multi-agent core | 77.8% | **77.8%** | 43.09s | 9,028 | $0.002083 | 9.86 |
| Multi-agent + Critic | 55.6% | 55.6% | 45.49s | 14,085 | $0.002873 | 10.00 |

### Benchmark offline có kiểm soát – 18 runs

| Kiến trúc | Hoàn thành | Hoàn thành + citation hợp lệ | Latency TB | Tokens TB | Cost TB/run | Quality* |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | **100%** | 33.3% | **13.93s** | **3,228** | **$0.000800** | 10.00 |
| Multi-agent core | 66.7% | **66.7%** | 39.12s | 13,376 | $0.002657 | 10.00 |
| Multi-agent + Critic | 33.3% | 33.3% | 46.03s | 18,446 | $0.003067 | 10.00 |

> **Kết luận chính:** baseline là mốc tốt nhất về tốc độ, chi phí và completion reliability. Core multi-agent có overhead lớn hơn nhưng đạt tỷ lệ **completed + strict citation-valid** cao nhất trong cả hai môi trường đánh giá. Critic chứng minh được bounded review loop, nhưng dữ liệu hiện tại chưa cho thấy lợi ích chất lượng đủ ổn định để bật mặc định.

\* Quality chỉ được tính trên các output có thể chấm. Judge 0–10 có hiện tượng ceiling effect, vì vậy quality không được diễn giải độc lập với completion rate, citation validity, latency, token, cost và failure mode.

## Kiến trúc

### Luồng core

```text
User Query
   ↓
Supervisor
   ↓
Researcher  → sources + research_notes
   ↓
Supervisor
   ↓
Analyst     → analysis_notes
   ↓
Supervisor
   ↓
Writer      → final_answer + citations
   ↓
Supervisor
   ↓
Done
```

### Luồng Critic bonus

```text
Writer
  ↓
Critic
  ├─ pass   → Done
  └─ revise → Writer → Critic → Done/Stop
```

Vòng sửa được giới hạn bằng `MAX_REVISIONS=1`; Critic không được search lại. Chế độ Critic mặc định **OFF** (`ENABLE_CRITIC=false`) để giữ core workflow đơn giản và phù hợp với kết quả benchmark.

## Guardrails đã triển khai

- `max_iterations` để chặn vòng lặp định tuyến vô hạn.
- Workflow timeout và provider timeout.
- Retry có giới hạn và backoff.
- Pydantic validation cho input/output có cấu trúc.
- Validation citation/source ở Writer.
- Fallback khi Analyst lỗi sau retry.
- Bounded Writer–Critic revision loop.
- Tracing theo hướng fail-open: LangSmith lỗi không làm workflow nghiên cứu bị crash.

## Cấu trúc repo

```text
.
├── src/multi_agent_research_lab/
│   ├── agents/              # Supervisor, Researcher, Analyst, Writer, Critic
│   ├── core/                # Config, schema, shared state, errors
│   ├── graph/               # LangGraph workflow
│   ├── runners/             # Baseline và multi-agent runners
│   ├── services/            # OpenRouter LLM, Tavily search
│   ├── evaluation/          # Online/offline benchmark + evaluator
│   └── observability/       # Logging và LangSmith tracing
├── data/offline_benchmark/  # 3 topic corpus được chọn cho controlled benchmark
├── demo/                    # Static showcase + Streamlit live demo
├── reports/                 # Final online/offline benchmark + trace evidence
├── docs/                    # Thiết kế, lab guide, rubric
├── tests/                   # Unit/integration tests với deterministic mocks
├── configs/
├── .env.example
├── pyproject.toml
├── uv.lock
└── Makefile
```

## Cài môi trường

Yêu cầu Python 3.11+ và `uv`.

```bash
uv sync --locked --extra dev --extra llm
```

Tạo `.env` từ `.env.example` và điền key cần thiết:

```text
OPENROUTER_API_KEY=...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-4o-mini
TAVILY_API_KEY=...
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=multi-agent-research-lab
LANGSMITH_TRACING=true
```

Không commit `.env` hoặc API key.

## Chạy hệ thống

### Single-agent baseline

```bash
uv run --locked python -m multi_agent_research_lab.cli baseline \
  --query "Research GraphRAG state-of-the-art and write a 500-word summary" \
  --max-sources 5 \
  --audience "technical learners"
```

### Multi-agent core

```bash
uv run --locked python -m multi_agent_research_lab.cli multi-agent \
  --query "Research GraphRAG state-of-the-art and write a 500-word summary" \
  --max-sources 5 \
  --audience "technical learners"
```

### Bật Critic bonus

PowerShell:

```powershell
$env:ENABLE_CRITIC="true"
$env:MAX_REVISIONS="1"
uv run --locked python -m multi_agent_research_lab.cli multi-agent --query "Compare single-agent and multi-agent workflows for customer support"
```

## Benchmark

### Benchmark online chính thức

Final artifact đã được lưu trong `reports/`. Nếu cần tái chạy:

```bash
uv run --locked python -m multi_agent_research_lab.evaluation.benchmark --repeats 3 --output-dir reports
```

### Benchmark offline có kiểm soát

```bash
uv run --locked python -m multi_agent_research_lab.evaluation.offline_benchmark \
  --topics AIAGENT-01 AIAGENT-12 AIAGENT-22 \
  --repeats 2 \
  --max-sources 5 \
  --corpus-dir data/offline_benchmark \
  --output-dir reports/offline_benchmark
```

Không gộp average của benchmark online và offline; hai thí nghiệm có mục tiêu khác nhau.

## LangSmith tracing

Evidence đã xác minh được lưu tại:

- `reports/trace_evidence.md`
- `reports/images/langsmith_multi_agent_trace.png`

Multi-agent trace cho thấy rõ Supervisor routing, Tavily search, từng LLM call và handoff giữa các agent. Tracing được thiết kế fail-open nên lỗi LangSmith không chặn kết quả nghiên cứu.

## Showcase demo

### Demo tĩnh – an toàn khi trình bày

```powershell
Start-Process .\demo\showcase.html
```

Trang này đọc số liệu đã cố định trong repo và không gọi API.

### Demo Streamlit – interactive + live

```powershell
uv run --locked --extra llm --with "streamlit>=1.38,<2" streamlit run demo/streamlit_app.py
```

Demo có ba phần:

1. **Tổng quan benchmark** – đọc trực tiếp final artifacts.
2. **Chạy nghiên cứu trực tiếp** – chọn online/offline và kiến trúc.
3. **Kiến trúc & trace** – giải thích route, Critic và LangSmith evidence.

Khi showcase, nên dùng **Multi-agent core + offline fixed corpus** cho live run vì không phụ thuộc Tavily.

## Quality gates

```bash
uv run --locked ruff check src tests demo
uv run --locked mypy src
uv run --locked pytest -q
```

Hoặc:

```bash
make lint
make typecheck
make test
```

## Tài liệu kết quả

- `reports/benchmark_report.md` – báo cáo benchmark online chính.
- `reports/offline_benchmark/benchmark_report.md` – benchmark offline có kiểm soát.
- `reports/trace_evidence.md` – trace và failure evidence.
- `docs/design_template.md` – quyết định kiến trúc và guardrail.
- `docs/lab_guide.md` – hướng dẫn + Exit Ticket đã trả lời.
- `demo/README.md` – cách showcase project.

## Khi nào nên dùng multi-agent?

Nên dùng khi bài toán cần **strict citation compliance**, khả năng audit từng bước, artefact trung gian và validation/retry rõ ràng; đặc biệt khi chi phí lỗi cao hơn chi phí orchestration.

Không nên dùng cho tác vụ đơn giản hoặc khi **latency, cost và completion reliability** là ưu tiên cao nhất. Benchmark của repo cho thấy thêm agent không tự động làm output tốt hơn; giá trị của orchestration phụ thuộc mục tiêu hệ thống.

## Ghi chú về corpus offline

Ba topic trong `data/offline_benchmark/` là subset do chủ Lab 20 cung cấp cho coursework. Package gốc không kèm standalone redistribution license, vì vậy cần giữ corpus trong phạm vi được chủ lab cho phép nếu public repo.

## Tham khảo

- Anthropic — Building Effective Agents
- OpenAI Agents SDK — orchestration / handoffs
- LangGraph — workflow/state graph
- LangSmith — tracing / observability
