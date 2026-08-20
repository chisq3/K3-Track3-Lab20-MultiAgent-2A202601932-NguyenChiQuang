"""Construction and resource ownership for the single-agent baseline."""

from contextlib import ExitStack

from multi_agent_research_lab.agents.baseline import BaselineAgent
from multi_agent_research_lab.agents.protocols import LLMCompletionClient, WebSearchClient
from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import ResearchTrace
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.search_client import SearchClient


def run_baseline(
    request: ResearchQuery,
    *,
    settings: Settings | None = None,
    llm_client: LLMCompletionClient | None = None,
    search_client: WebSearchClient | None = None,
) -> ResearchState:
    """Run a baseline, creating and closing only clients not supplied by the caller."""

    runtime_settings = settings or get_settings()
    state = ResearchState(request=request)
    with (
        ResearchTrace(
            state=state,
            settings=runtime_settings,
            architecture="baseline",
        ) as run_trace,
        ExitStack() as stack,
    ):
        resolved_llm: LLMCompletionClient
        resolved_search: WebSearchClient
        resolved_llm = (
            stack.enter_context(LLMClient(runtime_settings)) if llm_client is None else llm_client
        )
        resolved_search = (
            stack.enter_context(SearchClient(runtime_settings))
            if search_client is None
            else search_client
        )

        state = BaselineAgent(resolved_llm, resolved_search).run(state)
        run_trace.finish(state)
    return state
