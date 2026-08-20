"""Minimal service contracts injected into agents and test fakes."""

from typing import Protocol

from multi_agent_research_lab.core.schemas import SourceDocument
from multi_agent_research_lab.services.llm_client import LLMResponse


class LLMCompletionClient(Protocol):
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse: ...


class WebSearchClient(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]: ...
