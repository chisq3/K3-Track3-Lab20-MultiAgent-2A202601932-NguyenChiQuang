"""Production construction and resource ownership for the LangGraph workflow."""

from contextlib import ExitStack

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.critic import CriticAgent
from multi_agent_research_lab.agents.protocols import LLMCompletionClient, WebSearchClient
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.observability.tracing import ResearchTrace
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.search_client import SearchClient


def run_multi_agent(
    request: ResearchQuery,
    *,
    settings: Settings | None = None,
    llm_client: LLMCompletionClient | None = None,
    search_client: WebSearchClient | None = None,
) -> ResearchState:
    """Run the graph, creating and closing only clients not supplied by the caller."""

    runtime_settings = settings or get_settings()
    state = ResearchState(request=request)
    with (
        ResearchTrace(
            state=state,
            settings=runtime_settings,
            architecture="multi-agent",
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

        workflow_max_iterations = runtime_settings.effective_max_iterations
        supervisor = SupervisorAgent(
            max_iterations=workflow_max_iterations,
            timeout_seconds=runtime_settings.timeout_seconds,
            enable_critic=runtime_settings.enable_critic,
            max_revisions=runtime_settings.max_revisions,
        )
        workflow = MultiAgentWorkflow(
            supervisor=supervisor,
            researcher=ResearcherAgent(resolved_llm, resolved_search),
            analyst=AnalystAgent(resolved_llm),
            writer=WriterAgent(resolved_llm),
            max_iterations=workflow_max_iterations,
            critic=CriticAgent(resolved_llm) if runtime_settings.enable_critic else None,
        )
        state = workflow.run(state)
        run_trace.finish(state)
    return state
