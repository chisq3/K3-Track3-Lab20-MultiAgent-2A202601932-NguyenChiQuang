"""Public schemas exchanged between CLI, agents, and evaluators."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentName(StrEnum):
    BASELINE = "baseline"
    SUPERVISOR = "supervisor"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    WRITER = "writer"
    CRITIC = "critic"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class RouteName(StrEnum):
    BASELINE = "baseline"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    WRITER = "writer"
    CRITIC = "critic"
    DONE = "done"


class CriticDecision(StrEnum):
    PASS = "pass"
    REVISE = "revise"


class UsageMetrics(BaseModel):
    """Provider usage accumulated across one research run."""

    model_config = ConfigDict(validate_assignment=True)

    llm_calls: int = Field(default=0, ge=0)
    search_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    cost_complete: bool = True

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ResearchQuery(BaseModel):
    query: str = Field(..., min_length=5)
    max_sources: int = Field(default=5, ge=1, le=20)
    audience: str = "technical learners"


class AgentResult(BaseModel):
    agent: AgentName
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceDocument(BaseModel):
    title: str
    url: str | None = None
    snippet: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CriticResult(BaseModel):
    """Structured review returned by the optional Critic worker."""

    decision: CriticDecision
    quality_score: float = Field(ge=0, le=10)
    citation_coverage: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)
    citation_issues: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    revision_instructions: str | None = None

    @property
    def issue_count(self) -> int:
        """Return the total number of actionable findings across all categories."""

        return len(self.issues) + len(self.citation_issues) + len(self.unsupported_claims)


class QualityEvaluation(BaseModel):
    """Independent 0-10 rubric used by every benchmark variant."""

    relevance: float = Field(ge=0, le=2)
    completeness: float = Field(ge=0, le=2)
    factual_grounding: float = Field(ge=0, le=2)
    citation_correctness: float = Field(ge=0, le=2)
    clarity: float = Field(ge=0, le=2)
    rationale: str = Field(min_length=1)

    @property
    def total_score(self) -> float:
        return round(
            self.relevance
            + self.completeness
            + self.factual_grounding
            + self.citation_correctness
            + self.clarity,
            2,
        )


class BenchmarkCase(BaseModel):
    """One representative task reused unchanged across benchmark variants."""

    case_id: str = Field(min_length=1)
    query: str = Field(min_length=5)
    audience: str = "technical learners"
    max_sources: int = Field(default=5, ge=1, le=20)

    def to_request(self) -> ResearchQuery:
        return ResearchQuery(
            query=self.query,
            audience=self.audience,
            max_sources=self.max_sources,
        )


class BenchmarkMetrics(BaseModel):
    """Metrics for one architecture/query/repeat execution."""

    run_name: str
    query_id: str = ""
    query: str = ""
    audience: str = ""
    max_sources: int = Field(default=0, ge=0)
    repeat: int = Field(default=1, ge=1)
    status: RunStatus = RunStatus.PENDING
    stop_reason: str | None = None
    latency_seconds: float = Field(ge=0)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    cost_complete: bool = True
    search_calls: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    iterations: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_used: bool = False

    quality_score: float | None = Field(default=None, ge=0, le=10)
    citation_coverage: float | None = Field(default=None, ge=0, le=1)
    citation_validity: float | None = Field(default=None, ge=0, le=1)
    failure_rate: float | None = Field(default=None, ge=0, le=1)

    critic_decision: CriticDecision | None = None
    critic_quality_score: float | None = Field(default=None, ge=0, le=10)
    revision_count: int = Field(default=0, ge=0)

    judge_input_tokens: int = Field(default=0, ge=0)
    judge_output_tokens: int = Field(default=0, ge=0)
    judge_cost_usd: float | None = Field(default=None, ge=0)

    trace_id: str | None = None
    trace_url: str | None = None
    notes: str = ""


class BenchmarkSummary(BaseModel):
    """Aggregate metrics for one benchmark architecture."""

    run_name: str
    runs: int = Field(ge=1)
    success_rate: float = Field(ge=0, le=1)
    failure_rate: float = Field(ge=0, le=1)
    avg_latency_seconds: float = Field(ge=0)
    avg_total_tokens: float = Field(ge=0)
    avg_estimated_cost_usd: float | None = Field(default=None, ge=0)
    avg_quality_score: float | None = Field(default=None, ge=0, le=10)
    avg_citation_coverage: float | None = Field(default=None, ge=0, le=1)
    avg_citation_validity: float | None = Field(default=None, ge=0, le=1)
    avg_iterations: float = Field(default=0, ge=0)
    avg_revisions: float = Field(default=0, ge=0)
