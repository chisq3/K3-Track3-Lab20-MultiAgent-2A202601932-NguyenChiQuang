import pytest

from multi_agent_research_lab.core.errors import ValidationError
from multi_agent_research_lab.core.schemas import ResearchQuery, RouteName
from multi_agent_research_lab.core.state import ResearchState


def test_state_records_route_and_trace() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    state.record_route("researcher")
    state.add_trace_event("route", {"next": "researcher"})
    assert state.iteration == 1
    assert state.route_history == ["researcher"]
    assert state.trace[0]["name"] == "route"
    assert state.next_route is RouteName.RESEARCHER


def test_state_accumulates_usage_and_step_durations() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))

    state.record_search_call()
    state.record_llm_usage(input_tokens=100, output_tokens=25, cost_usd=0.001)
    state.record_llm_usage(input_tokens=20, output_tokens=5, cost_usd=None)
    state.record_step_duration("llm", 0.25)
    state.record_step_duration("llm", 0.5)

    assert state.usage.search_calls == 1
    assert state.usage.llm_calls == 2
    assert state.usage.total_tokens == 150
    assert state.usage.estimated_cost_usd == pytest.approx(0.001)
    assert state.usage.cost_complete is False
    assert state.step_durations_seconds["llm"] == pytest.approx(0.75)


def test_state_rejects_unknown_route_and_negative_metrics() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))

    with pytest.raises(ValidationError, match="Unknown workflow route"):
        state.record_route("unknown")
    with pytest.raises(ValidationError, match="input_tokens"):
        state.record_llm_usage(input_tokens=-1, output_tokens=0, cost_usd=0)
    with pytest.raises(ValidationError, match="duration_seconds"):
        state.record_step_duration("research", -0.1)
