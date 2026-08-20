"""Sequential worker runner used to validate handoffs before graph orchestration."""

from contextlib import ExitStack
from time import perf_counter

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.protocols import LLMCompletionClient, WebSearchClient
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.errors import LabError
from multi_agent_research_lab.core.schemas import ResearchQuery, RouteName, RunStatus
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.search_client import SearchClient


def run_worker_pipeline(
    request: ResearchQuery,
    *,
    llm_client: LLMCompletionClient | None = None,
    search_client: WebSearchClient | None = None,
) -> ResearchState:
    """Run Researcher, Analyst, and Writer in a deterministic integration path."""

    with ExitStack() as stack:
        resolved_llm: LLMCompletionClient
        resolved_search: WebSearchClient
        resolved_llm = stack.enter_context(LLMClient()) if llm_client is None else llm_client
        resolved_search = (
            stack.enter_context(SearchClient()) if search_client is None else search_client
        )

        state = ResearchState(request=request, status=RunStatus.RUNNING)
        started = perf_counter()
        state.add_trace_event("worker_pipeline_started", {"query": request.query})

        try:
            state.record_route(RouteName.RESEARCHER)
            ResearcherAgent(resolved_llm, resolved_search).run(state)

            state.record_route(RouteName.ANALYST)
            AnalystAgent(resolved_llm).run(state)

            state.record_route(RouteName.WRITER)
            WriterAgent(resolved_llm).run(state)

            state.status = RunStatus.COMPLETED
            state.next_route = RouteName.DONE
            state.add_trace_event(
                "worker_pipeline_completed",
                {
                    "agent_count": len(state.agent_results),
                    "total_tokens": state.usage.total_tokens,
                },
            )
            return state
        except LabError as exc:
            state.status = RunStatus.FAILED
            state.next_route = RouteName.DONE
            state.add_trace_event("worker_pipeline_failed", {"error": str(exc)})
            raise
        finally:
            state.record_step_duration("worker_pipeline_total", perf_counter() - started)
