"""Command-line entrypoint for the lab starter."""

from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import LabError
from multi_agent_research_lab.core.schemas import ResearchQuery, RunStatus
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.logging import configure_logging
from multi_agent_research_lab.runners import run_baseline, run_multi_agent

app = typer.Typer(help="Multi-Agent Research Lab starter CLI")
console = Console()


def _init() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)


def _parse_query(
    query: str, max_sources: int = 5, audience: str = "technical learners"
) -> ResearchQuery:
    try:
        return ResearchQuery(query=query, max_sources=max_sources, audience=audience)
    except ValidationError as exc:
        console.print(
            Panel.fit(
                f"Invalid query: {exc.errors()[0]['msg']}",
                title="Input Error",
                style="red",
            )
        )
        raise typer.Exit(code=1) from exc


@app.command()
def baseline(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
    max_sources: Annotated[
        int, typer.Option("--max-sources", min=1, max=20, help="Maximum web sources")
    ] = 5,
    audience: Annotated[
        str, typer.Option("--audience", help="Intended audience for the answer")
    ] = "technical learners",
) -> None:
    """Run the measured single-agent research baseline."""

    _init()
    request = _parse_query(query, max_sources=max_sources, audience=audience)
    try:
        state = run_baseline(request)
    except LabError as exc:
        console.print(Panel.fit(str(exc), title="Baseline Failed", style="red"))
        raise typer.Exit(code=2) from exc

    answer = state.final_answer or "Baseline completed without a final answer."
    console.print(Panel(answer, title="Single-Agent Baseline", border_style="green"))
    console.print(Panel.fit(_format_baseline_metrics(state), title="Run Metrics"))


@app.command("multi-agent")
def multi_agent(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
    max_sources: Annotated[
        int, typer.Option("--max-sources", min=1, max=20, help="Maximum web sources")
    ] = 5,
    audience: Annotated[
        str, typer.Option("--audience", help="Intended audience for the answer")
    ] = "technical learners",
) -> None:
    """Run the Supervisor-orchestrated LangGraph workflow."""

    _init()
    request = _parse_query(query, max_sources=max_sources, audience=audience)
    try:
        state = run_multi_agent(request)
    except LabError as exc:
        console.print(Panel.fit(str(exc), title="Multi-Agent Failed", style="red"))
        raise typer.Exit(code=2) from exc

    if state.status is RunStatus.FAILED:
        failure = "\n".join(state.errors) or state.stop_reason or "Workflow failed"
        console.print(Panel.fit(failure, title="Multi-Agent Failed", style="red"))
        console.print(Panel.fit(_format_multi_agent_metrics(state), title="Run Metrics"))
        raise typer.Exit(code=2)

    answer = state.final_answer or "Workflow completed without a final answer."
    border_style = "yellow" if state.errors else "green"
    console.print(Panel(answer, title="Multi-Agent Answer", border_style=border_style))
    console.print(Panel.fit(_format_multi_agent_metrics(state), title="Run Metrics"))
    if state.errors:
        console.print(
            Panel.fit("\n".join(f"- {error}" for error in state.errors), title="Warnings")
        )


def _format_baseline_metrics(state: ResearchState) -> str:
    total_latency = state.step_durations_seconds.get("baseline_total", 0.0)
    if state.usage.cost_complete:
        cost = f"${state.usage.estimated_cost_usd:.6f}"
    else:
        cost = "unavailable (provider omitted cost)"
    tracing = _format_trace_reference(state)
    return (
        f"Status: {state.status.value}\n"
        f"Sources: {len(state.sources)}\n"
        f"Latency: {total_latency:.2f}s\n"
        f"Tokens: {state.usage.total_tokens} "
        f"({state.usage.input_tokens} input, {state.usage.output_tokens} output)\n"
        f"Estimated cost: {cost}\n"
        f"{tracing}"
    )


def _format_multi_agent_metrics(state: ResearchState) -> str:
    total_latency = state.step_durations_seconds.get("workflow_total", 0.0)
    routes = " -> ".join(route.value for route in state.route_history)
    if state.usage.cost_complete:
        cost = f"${state.usage.estimated_cost_usd:.6f}"
    else:
        cost = "unavailable (provider omitted cost)"
    tracing = _format_trace_reference(state)
    critic = _format_critic_metrics(state)
    return (
        f"Status: {state.status.value}\n"
        f"Routes: {routes}\n"
        f"Iterations: {state.iteration}\n"
        f"Stop reason: {state.stop_reason or 'not recorded'}\n"
        f"Sources: {len(state.sources)}\n"
        f"Calls: {state.usage.search_calls} search, {state.usage.llm_calls} LLM\n"
        f"Retries: {state.retry_count}\n"
        f"{critic}\n"
        f"Latency: {total_latency:.2f}s\n"
        f"Tokens: {state.usage.total_tokens} "
        f"({state.usage.input_tokens} input, {state.usage.output_tokens} output)\n"
        f"Estimated cost: {cost}\n"
        f"{tracing}"
    )


def _format_critic_metrics(state: ResearchState) -> str:
    if not state.critic_history:
        return "Critic: disabled or not reached"
    latest = state.critic_history[-1]
    return (
        f"Critic: {latest.decision.value}, {len(state.critic_history)} review(s), "
        f"{state.revision_count} revision(s), quality {latest.quality_score:.1f}/10, "
        f"citation coverage {latest.citation_coverage:.0%}"
    )


def _format_trace_reference(state: ResearchState) -> str:
    if state.trace_url:
        return f"Trace: {state.trace_url}"
    if state.trace_id:
        return f"Trace ID: {state.trace_id} (URL unavailable)"
    return "Trace: disabled or unavailable"


if __name__ == "__main__":
    app()
