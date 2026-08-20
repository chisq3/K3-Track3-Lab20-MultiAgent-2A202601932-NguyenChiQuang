# Demo Showcase Lab 20

Thư mục `demo/` là lớp trình diễn của hệ thống Lab 20. Demo **không duplicate** Supervisor, Researcher, Analyst, Writer, Critic hoặc workflow logic; live mode import trực tiếp production runners trong `src/`.

## Hai chế độ showcase

### 1. Trang tĩnh – khuyến nghị khi thuyết trình

`showcase.html` đọc các kết quả đã chốt và không gọi API. Đây là phương án an toàn nhất khi demo trước lớp hoặc grading vì network/provider lỗi không thể che mất benchmark evidence.

```powershell
Start-Process .\demo\showcase.html
```

### 2. Streamlit – interactive + live research

```powershell
uv run --locked --extra llm --with "streamlit>=1.38,<2" streamlit run demo/streamlit_app.py
```

`--with` chỉ cài Streamlit tạm thời, không thay đổi `pyproject.toml` hoặc `uv.lock`.

## Flow trình bày đề xuất

1. Mở **Tổng quan benchmark** và giới thiệu benchmark online 27 runs.
2. Chuyển sang controlled offline 18 runs để giải thích fixed evidence/reproducibility.
3. Nhấn mạnh **Valid completed** thay vì chỉ nhìn quality score.
4. Mở **Kiến trúc & trace** để giải thích Supervisor routing và LangSmith evidence.
5. Nếu cần live run, chọn **Offline · corpus cố định / Multi-agent core**.
6. Giải thích Critic là bonus assurance mode, không phải default architecture.

## Biến môi trường cho live mode

```text
OPENROUTER_API_KEY=...        # bắt buộc cho live generation
TAVILY_API_KEY=...            # chỉ cần ở Online · Tavily
LANGSMITH_API_KEY=...         # tùy chọn
LANGSMITH_TRACING=true        # tùy chọn
```

Không đặt secret trong source demo và không commit `.env`.

## Thông điệp showcase chính

- Baseline là mốc tốt nhất về speed/cost/completion reliability.
- Core multi-agent đạt valid-completed rate cao nhất trong cả online và controlled offline benchmark.
- Critic bounded loop hoạt động nhưng làm tăng token/cost/failure surface; vì vậy giữ `ENABLE_CRITIC=false` mặc định là phù hợp với dữ liệu.
