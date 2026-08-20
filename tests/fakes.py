"""Deterministic service fakes reused by agent and workflow unit tests."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from multi_agent_research_lab.core.schemas import SourceDocument
from multi_agent_research_lab.services.llm_client import LLMResponse


@dataclass(frozen=True)
class LLMCall:
    system_prompt: str
    user_prompt: str
    temperature: float
    max_tokens: int | None
    model: str | None


class MockLLMClient:
    """Return queued responses without network access and record every call."""

    def __init__(self, responses: list[LLMResponse | Exception]) -> None:
        self._responses = deque(responses)
        self.calls: list[LLMCall] = []

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        self.calls.append(LLMCall(system_prompt, user_prompt, temperature, max_tokens, model))
        if not self._responses:
            raise AssertionError("MockLLMClient has no queued response")
        outcome = self._responses.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class MockSearchClient:
    """Return a defensive copy of fixed sources and record search requests."""

    def __init__(
        self,
        sources: list[SourceDocument],
        error: Exception | None = None,
    ) -> None:
        self._sources = sources
        self._error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        self.calls.append((query, max_results))
        if self._error is not None:
            raise self._error
        return [source.model_copy(deep=True) for source in self._sources[:max_results]]
