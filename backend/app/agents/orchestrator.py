"""MAF workflow orchestrator.

Coordinates the agent pipeline: sequences agents, threads the shared context,
handles failures (stopping on the first failed agent), retries recoverable
failures (via each agent's base-class logic), logs each step, and measures
execution time. Returns a structured :class:`WorkflowRunResult` (including the
full execution trace) suitable for an API response.

Phase 1: agents return mock success; no business modules are invoked.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from app.agents.base import AgentStatus
from app.agents.context import WorkflowContext, WorkflowState
from app.agents.logging import get_workflow_logger
from app.agents.retry import RetryPolicy
from app.agents.timing import Stopwatch
from app.agents.trace import AgentStepTrace
from app.agents.workflow import AgentWorkflow

logger = get_workflow_logger()


class WorkflowRunResult(BaseModel):
    """The outcome of a workflow run, returned to the API."""

    run_id: str
    business_date: str
    workflow: str
    state: str
    message: str
    completed_agents: list[str] = Field(default_factory=list)
    steps: list[AgentStepTrace] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    pending_gate: str | None = None


class WorkflowOrchestrator:
    """Runs an :class:`AgentWorkflow`, handling sequencing and failures."""

    def __init__(self, workflow: AgentWorkflow, retry: RetryPolicy | None = None) -> None:
        self._workflow = workflow
        self._retry = retry or RetryPolicy()

    @property
    def workflow(self) -> AgentWorkflow:
        """The workflow this orchestrator runs."""
        return self._workflow

    def run(
        self, business_date: str, params: dict | None = None
    ) -> WorkflowRunResult:
        """Execute the workflow for ``business_date`` and return the result."""
        context = WorkflowContext(
            run_id=uuid4().hex, business_date=business_date, params=params or {}
        )
        return self.run_with_context(context)

    def run_with_context(
        self,
        context: WorkflowContext,
        pause_after: frozenset[str] | set[str] | None = None,
    ) -> WorkflowRunResult:
        """Run the agents on a caller-provided context and return the result.

        The context is mutated in place, so callers may inspect
        ``context.shared`` for the produced artifacts after this returns.

        Execution resumes from ``context.next_index`` (0 for a fresh run). When
        an agent named in ``pause_after`` completes and has not been approved,
        the workflow stops with state ``AWAITING_APPROVAL`` and records the
        ``pending_gate``; a later call (after recording the approval) resumes
        from the next agent without re-running completed ones.
        """
        gates = frozenset(pause_after or ())
        business_date = context.business_date
        context.state = WorkflowState.RUNNING
        context.pending_gate = None
        agents = self._workflow.agents
        logger.info(
            "Running workflow '%s' run %s for %s from step %d.",
            self._workflow.name,
            context.run_id,
            business_date,
            context.next_index,
        )

        message = "Workflow completed successfully."
        with Stopwatch() as sw:
            while context.next_index < len(agents):
                agent = agents[context.next_index]
                result = agent.run(context, self._retry)
                if result.status is AgentStatus.FAILED:
                    context.state = WorkflowState.FAILED
                    message = f"Workflow failed at agent '{agent.name}': {result.error}"
                    logger.error(message)
                    break
                context.next_index += 1

                # Human-in-the-loop gate: pause after this agent if required and
                # not yet approved.
                if agent.name in gates and not context.approvals.get(agent.name):
                    context.state = WorkflowState.AWAITING_APPROVAL
                    context.pending_gate = agent.name
                    message = f"Awaiting approval after agent '{agent.name}'."
                    logger.info(message)
                    break
            else:
                context.state = WorkflowState.COMPLETED

        logger.info(
            "Workflow '%s' run %s -> %s (%.1f ms).",
            self._workflow.name,
            context.run_id,
            context.state.value,
            sw.elapsed_ms,
        )

        return WorkflowRunResult(
            run_id=context.run_id,
            business_date=business_date,
            workflow=self._workflow.name,
            state=context.state.value,
            message=message,
            completed_agents=context.trace.completed_agents(),
            steps=context.trace.steps,
            total_duration_ms=sw.elapsed_ms,
            pending_gate=context.pending_gate,
        )
