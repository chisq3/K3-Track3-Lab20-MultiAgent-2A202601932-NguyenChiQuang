from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest

from multi_agent_research_lab.core.config import Settings
from multi_agent_research_lab.core.schemas import ResearchQuery, RunStatus
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability import tracing


class FakeRun:
    id = UUID("12345678-1234-5678-1234-567812345678")
    trace_id = id

    def __init__(self) -> None:
        self.outputs: dict[str, object] | None = None
        self.metadata: dict[str, object] | None = None

    def end(
        self,
        *,
        outputs: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.outputs = outputs
        self.metadata = metadata


class FakeClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.flushed = False

    def flush(self) -> None:
        self.flushed = True

    def read_run(self, run_id: UUID) -> object:
        assert run_id == FakeRun.id
        return object()

    def get_run_url(self, *, run: object, project_name: str) -> str:
        assert run is not None
        assert project_name == "trace-tests"
        return "https://smith.langchain.com/trace/test"


def test_research_trace_records_id_url_and_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_run = FakeRun()
    fake_client = FakeClient()

    @contextmanager
    def fake_context(**_: object) -> Iterator[None]:
        yield

    @contextmanager
    def fake_trace(*_: object, **__: object) -> Iterator[FakeRun]:
        yield fake_run

    monkeypatch.setattr(tracing, "Client", lambda **_: fake_client)
    monkeypatch.setattr(tracing, "tracing_context", fake_context)
    monkeypatch.setattr(tracing, "trace", fake_trace)

    state = ResearchState(request=ResearchQuery(query="Trace a research workflow"))
    settings = Settings(
        _env_file=None,
        LANGSMITH_API_KEY="test-key",
        LANGSMITH_PROJECT="trace-tests",
        LANGSMITH_TRACING=True,
    )

    with tracing.ResearchTrace(
        state=state,
        settings=settings,
        architecture="multi-agent",
    ) as run_trace:
        state.status = RunStatus.COMPLETED
        state.record_llm_usage(input_tokens=10, output_tokens=5, cost_usd=0.001)
        run_trace.finish(state)

    assert state.trace_id == str(FakeRun.trace_id)
    assert state.trace_url == "https://smith.langchain.com/trace/test"
    assert fake_client.flushed is True
    assert fake_run.outputs is not None
    assert fake_run.outputs["status"] == "completed"
    assert "test-key" not in repr(fake_run.outputs)
    assert state.trace[-1]["name"] == "langsmith_trace_completed"


@pytest.mark.parametrize(
    ("enabled", "api_key", "reason"),
    [(False, "test-key", "disabled"), (True, None, "missing_api_key")],
)
def test_research_trace_skips_without_remote_calls(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    api_key: str | None,
    reason: str,
) -> None:
    def unexpected_client(**_: object) -> None:
        raise AssertionError("LangSmith client should not be constructed")

    monkeypatch.setattr(tracing, "Client", unexpected_client)
    state = ResearchState(request=ResearchQuery(query="Trace skip behavior"))
    settings = Settings(
        _env_file=None,
        LANGSMITH_API_KEY=api_key,
        LANGSMITH_TRACING=enabled,
    )

    with tracing.ResearchTrace(
        state=state,
        settings=settings,
        architecture="baseline",
    ) as run_trace:
        state.status = RunStatus.COMPLETED
        run_trace.finish(state)

    assert state.trace_id is None
    assert state.trace_url is None
    assert state.trace[0] == {
        "name": "langsmith_tracing_skipped",
        "payload": {"reason": reason},
    }


def test_trace_span_setup_failure_does_not_mask_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenContext:
        def __enter__(self) -> None:
            raise RuntimeError("tracer unavailable")

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(tracing, "get_tracing_context", lambda: {"enabled": True})
    monkeypatch.setattr(tracing, "trace", lambda *_args, **_kwargs: BrokenContext())

    with tracing.trace_span("provider-call", {"query": "safe"}) as span:
        span["outputs"] = {"result": "completed"}

    assert span["outputs"] == {"result": "completed"}
    assert isinstance(span["duration_seconds"], float)


def test_root_metadata_does_not_include_provider_credentials() -> None:
    state = ResearchState(request=ResearchQuery(query="Inspect safe metadata"))

    settings = Settings(
        _env_file=None,
        ENABLE_CRITIC=False,
        OPENROUTER_API_KEY="openrouter-secret",
        TAVILY_API_KEY="tavily-secret",
        LANGSMITH_API_KEY="langsmith-secret",
    )

    metadata: dict[str, Any] = tracing._root_metadata(
        state,
        settings,
        "multi-agent",
    )

    rendered = repr(metadata)

    assert "openrouter-secret" not in rendered
    assert "tavily-secret" not in rendered
    assert "langsmith-secret" not in rendered
    assert metadata["critic_enabled"] is False
