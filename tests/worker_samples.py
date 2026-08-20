"""Reusable deterministic evidence for worker-agent tests."""

from multi_agent_research_lab.core.schemas import SourceDocument


def sample_sources() -> list[SourceDocument]:
    return [
        SourceDocument(
            title="Coordination through shared state",
            url="https://example.com/shared-state",
            snippet="Specialized agents can coordinate by reading and updating shared state.",
        ),
        SourceDocument(
            title="Multi-agent system trade-offs",
            url="https://example.com/trade-offs",
            snippet="Additional agent calls can improve specialization but add latency and cost.",
        ),
    ]
