"""Shared state for baseline and multi-agent research workflows."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import (
    AgentName,
    AgentResult,
    CriticResult,
    ResearchQuery,
    RouteName,
    RunStatus,
    SourceDocument,
    UsageMetrics,
)


class ResearchState(BaseModel):
    """Single source of truth passed through the workflow."""

    model_config = ConfigDict(validate_assignment=True)

    request: ResearchQuery
    status: RunStatus = RunStatus.PENDING
    next_route: RouteName | None = None
    iteration: int = 0
    route_history: list[RouteName] = Field(default_factory=list)

    sources: list[SourceDocument] = Field(default_factory=list)
    research_notes: str | None = None
    analysis_notes: str | None = None
    final_answer: str | None = None
    critic_result: CriticResult | None = None
    critic_history: list[CriticResult] = Field(default_factory=list)
    revision_count: int = Field(default=0, ge=0)

    agent_results: list[AgentResult] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    agent_attempts: dict[AgentName, int] = Field(default_factory=dict)
    retry_count: int = 0
    last_failed_agent: AgentName | None = None
    fallback_used: bool = False
    stop_reason: str | None = None
    usage: UsageMetrics = Field(default_factory=UsageMetrics)
    step_durations_seconds: dict[str, float] = Field(default_factory=dict)
    trace_id: str | None = None
    trace_url: str | None = None

    def record_route(self, route: RouteName | str) -> None:
        try:
            normalized_route = RouteName(route)
        except ValueError as exc:
            raise ValidationError(f"Unknown workflow route: {route}") from exc
        self.route_history.append(normalized_route)
        self.next_route = normalized_route
        self.iteration += 1

    def add_trace_event(self, name: str, payload: dict[str, Any]) -> None:
        self.trace.append({"name": name, "payload": payload})

    def record_search_call(self) -> None:
        self.usage.search_calls += 1

    def record_llm_usage(
        self,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
    ) -> None:
        """Accumulate one successful LLM response without depending on a provider type."""

        for field_name, value in (
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
        ):
            if value is not None and value < 0:
                raise ValidationError(f"{field_name} must not be negative")
        if cost_usd is not None and cost_usd < 0:
            raise ValidationError("cost_usd must not be negative")

        self.usage.llm_calls += 1
        self.usage.input_tokens += input_tokens or 0
        self.usage.output_tokens += output_tokens or 0
        if cost_usd is None:
            self.usage.cost_complete = False
        else:
            self.usage.estimated_cost_usd += cost_usd

    def record_step_duration(self, step: str, duration_seconds: float) -> None:
        clean_step = step.strip()
        if not clean_step:
            raise ValidationError("step name must not be empty")
        if duration_seconds < 0:
            raise ValidationError("duration_seconds must not be negative")
        previous_duration = self.step_durations_seconds.get(clean_step, 0.0)
        self.step_durations_seconds[clean_step] = previous_duration + duration_seconds
