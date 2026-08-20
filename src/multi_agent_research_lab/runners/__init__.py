"""Reusable entrypoints for baseline and workflow executions."""

from multi_agent_research_lab.runners.baseline import run_baseline
from multi_agent_research_lab.runners.multi_agent import run_multi_agent
from multi_agent_research_lab.runners.workers import run_worker_pipeline

__all__ = ["run_baseline", "run_multi_agent", "run_worker_pipeline"]
