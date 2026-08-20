.PHONY: install test lint format typecheck run-baseline run-multi clean

install:
	uv sync --locked --extra dev --extra llm

test:
	uv run --locked pytest

lint:
	uv run --locked ruff check src tests

format:
	uv run --locked ruff format src tests

typecheck:
	uv run --locked mypy src

run-baseline:
	uv run --locked python -m multi_agent_research_lab.cli baseline --query "Research GraphRAG state-of-the-art"

run-multi:
	uv run --locked python -m multi_agent_research_lab.cli multi-agent --query "Research GraphRAG state-of-the-art"

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build *.egg-info
