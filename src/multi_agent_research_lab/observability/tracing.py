"""Fail-open local and LangSmith tracing helpers.

The application always keeps lightweight events in ``ResearchState.trace``. When
LangSmith is enabled and configured, these helpers additionally create a remote root
trace and nested spans without exposing provider credentials.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from time import perf_counter
from types import TracebackType
from typing import Any, Literal

from langsmith import Client
from langsmith.run_helpers import get_tracing_context, trace, tracing_context
from langsmith.run_trees import RunTree

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.core.state import ResearchState

logger = logging.getLogger(__name__)

TraceRunType = Literal["tool", "chain", "llm", "retriever", "embedding", "prompt", "parser"]


class ResearchTrace(AbstractContextManager["ResearchTrace"]):
    """Own one optional LangSmith root trace for a complete research run."""

    def __init__(
        self,
        *,
        state: ResearchState,
        settings: Settings,
        architecture: str,
    ) -> None:
        self._initial_state = state
        self._result_state = state
        self._settings = settings
        self._architecture = architecture
        self._stack: ExitStack | None = None
        self._client: Client | None = None
        self._root: RunTree | None = None

    def __enter__(self) -> ResearchTrace:
        reason = _tracing_skip_reason(self._settings)
        if reason is not None:
            self._initial_state.add_trace_event(
                "langsmith_tracing_skipped",
                {"reason": reason},
            )
            return self

        stack = ExitStack()
        try:
            client = Client(
                api_key=self._settings.langsmith_api_key,
                api_url=self._settings.langsmith_endpoint,
                workspace_id=self._settings.langsmith_workspace_id,
            )
            stack.enter_context(
                tracing_context(
                    enabled=True,
                    client=client,
                    project_name=self._settings.langsmith_project,
                    tags=[self._architecture, self._settings.app_env],
                    metadata=_root_metadata(
                        self._initial_state,
                        self._settings,
                        self._architecture,
                    ),
                )
            )
            root = stack.enter_context(
                trace(
                    _root_run_name(self._architecture),
                    run_type="chain",
                    inputs=_root_inputs(self._initial_state),
                    client=client,
                    project_name=self._settings.langsmith_project,
                    tags=[self._architecture, self._settings.app_env],
                    metadata=_root_metadata(
                        self._initial_state,
                        self._settings,
                        self._architecture,
                    ),
                )
            )
        except Exception as exc:
            _close_stack_safely(stack)
            self._record_unavailable("setup", exc)
            return self

        self._stack = stack
        self._client = client
        self._root = root
        self._initial_state.trace_id = str(root.trace_id)
        self._initial_state.add_trace_event(
            "langsmith_trace_started",
            {"trace_id": self._initial_state.trace_id},
        )
        return self

    def finish(self, state: ResearchState) -> None:
        """Attach the final state summary before closing the remote root span."""

        self._result_state = state
        if self._root is None:
            return

        state.trace_id = str(self._root.trace_id)
        try:
            self._root.end(
                outputs=_root_outputs(state),
                metadata=_completion_metadata(state),
            )
        except Exception as exc:
            self._record_unavailable("output", exc)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        stack = self._stack
        if stack is None:
            return False

        try:
            stack.__exit__(exc_type, exc_value, traceback)
        except Exception as exc:
            self._record_unavailable("upload", exc)
        finally:
            self._stack = None

        if exc_type is None:
            self._resolve_trace_url()
        return False

    def _resolve_trace_url(self) -> None:
        if self._client is None or self._root is None:
            return

        try:
            self._client.flush()
            remote_run = self._client.read_run(self._root.id)
            trace_url = self._client.get_run_url(
                run=remote_run,
                project_name=self._settings.langsmith_project,
            )
        except Exception as exc:
            self._record_unavailable("url", exc)
            return

        self._result_state.trace_url = trace_url
        self._result_state.add_trace_event(
            "langsmith_trace_completed",
            {
                "trace_id": self._result_state.trace_id,
                "trace_url": trace_url,
            },
        )

    def _record_unavailable(self, stage: str, exc: BaseException) -> None:
        reason = type(exc).__name__
        logger.warning("LangSmith tracing unavailable during %s: %s", stage, reason)
        self._result_state.add_trace_event(
            "langsmith_tracing_unavailable",
            {"stage": stage, "reason": reason},
        )


@contextmanager
def trace_span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
    *,
    run_type: TraceRunType = "chain",
) -> Iterator[dict[str, Any]]:
    """Create a timed local span and, inside an active run, a LangSmith child span.

    Tracing setup and upload errors never mask the provider operation. Callers may set
    ``span["outputs"]`` to a JSON-safe summary before leaving the context.
    """

    started = perf_counter()
    safe_attributes = dict(attributes or {})
    span: dict[str, Any] = {
        "name": name,
        "attributes": safe_attributes,
        "outputs": None,
        "duration_seconds": None,
    }

    if not get_tracing_context().get("enabled"):
        try:
            yield span
        finally:
            span["duration_seconds"] = perf_counter() - started
        return

    remote_context = trace(
        name,
        run_type=run_type,
        inputs=safe_attributes,
    )
    try:
        remote_run = remote_context.__enter__()
    except Exception as exc:
        logger.warning("LangSmith child span setup failed for %s: %s", name, type(exc).__name__)
        try:
            yield span
        finally:
            span["duration_seconds"] = perf_counter() - started
        return

    try:
        yield span
    except BaseException:
        span["duration_seconds"] = perf_counter() - started
        try:
            remote_context.__exit__(*sys.exc_info())
        except Exception as trace_exc:
            logger.warning(
                "LangSmith child span upload failed for %s: %s",
                name,
                type(trace_exc).__name__,
            )
        raise
    else:
        span["duration_seconds"] = perf_counter() - started
        try:
            outputs = span.get("outputs")
            remote_run.end(
                outputs=outputs if isinstance(outputs, dict) else {},
                metadata={"duration_seconds": span["duration_seconds"]},
            )
            remote_context.__exit__(None, None, None)
        except Exception as exc:
            logger.warning(
                "LangSmith child span upload failed for %s: %s",
                name,
                type(exc).__name__,
            )


def _tracing_skip_reason(settings: Settings) -> str | None:
    if not settings.langsmith_tracing:
        return "disabled"
    if settings.langsmith_api_key is None or not settings.langsmith_api_key.strip():
        return "missing_api_key"
    return None


def _root_run_name(architecture: str) -> str:
    return "single-agent-baseline" if architecture == "baseline" else "multi-agent-research"


def _root_inputs(state: ResearchState) -> dict[str, object]:
    return {
        "query": state.request.query,
        "max_sources": state.request.max_sources,
        "audience": state.request.audience,
    }


def _root_metadata(
    state: ResearchState,
    settings: Settings,
    architecture: str,
) -> dict[str, object]:
    return {
        "architecture": architecture,
        "app_env": settings.app_env,
        "model": settings.openai_model,
        "max_iterations": settings.max_iterations,
        "effective_max_iterations": settings.effective_max_iterations,
        "timeout_seconds": settings.timeout_seconds,
        "max_sources": state.request.max_sources,
        "critic_enabled": settings.enable_critic,
        "max_revisions": settings.max_revisions if settings.enable_critic else 0,
    }


def _root_outputs(state: ResearchState) -> dict[str, object]:
    return {
        "status": state.status.value,
        "stop_reason": state.stop_reason,
        "routes": [route.value for route in state.route_history],
        "source_count": len(state.sources),
        "has_final_answer": bool(state.final_answer),
        "retry_count": state.retry_count,
        "fallback_used": state.fallback_used,
        "critic_reviews": len(state.critic_history),
        "revision_count": state.revision_count,
        "critic_decision": (
            state.critic_history[-1].decision.value if state.critic_history else None
        ),
        "usage": state.usage.model_dump(mode="json"),
    }


def _completion_metadata(state: ResearchState) -> dict[str, object]:
    return {
        "status": state.status.value,
        "iterations": state.iteration,
        "llm_calls": state.usage.llm_calls,
        "search_calls": state.usage.search_calls,
        "total_tokens": state.usage.total_tokens,
        "estimated_cost_usd": state.usage.estimated_cost_usd,
        "critic_reviews": len(state.critic_history),
        "revision_count": state.revision_count,
    }


def _close_stack_safely(stack: ExitStack) -> None:
    try:
        stack.close()
    except Exception:
        logger.debug("Ignoring LangSmith cleanup error", exc_info=True)
