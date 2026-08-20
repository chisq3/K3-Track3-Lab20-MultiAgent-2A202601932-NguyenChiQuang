FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra llm

COPY configs ./configs
COPY docs ./docs

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "-m", "multi_agent_research_lab.cli"]
