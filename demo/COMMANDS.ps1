# Lệnh showcase Lab 20 - chạy từ root repo.

# 1) Quality gates
uv run --locked ruff check src tests demo
uv run --locked mypy src
uv run --locked pytest -q
uv run --locked python -m py_compile demo/streamlit_app.py

# 2) Mở showcase tĩnh - không gọi API
Start-Process .\demo\showcase.html

# 3) Chạy Streamlit interactive/live demo
uv run --locked --extra llm --with "streamlit>=1.38,<2" streamlit run demo/streamlit_app.py

# 4) Nếu cần kiểm tra final benchmark artifacts
(Get-Content .\reports\benchmark_raw.jsonl).Count
(Get-Content .\reports\offline_benchmark\benchmark_raw.jsonl).Count
Get-Content .\reports\benchmark_summary.csv
Get-Content .\reports\offline_benchmark\benchmark_summary.csv
