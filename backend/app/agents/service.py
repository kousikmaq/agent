"""MAF orchestration service.

Runs the agent workflow, collects the artifacts the agents produced into the
shared context, optionally persists them via the existing ``ResultsStore`` (so
the same ``outputs/<date>/`` files back the existing GET endpoints and the
frontend), and returns a full, typed result including the explanation answer.

Also supports Human-in-the-Loop (HITL) approval gates: the workflow can pause
after configured agents and resume once a planner approves, without re-running
completed agents. Paused runs are held in an in-memory registry keyed by run id.

This is a thin coordination layer - it introduces no business logic and reuses
the existing persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agents.analytics_agent import KPIS_KEY
from app.agents.context import WorkflowContext, WorkflowState
from app.agents.explanation_agent import (
    EXPLANATION_ANSWER_KEY,
    EXPLANATION_CONTEXT_KEY,
    EXPLANATION_SUMMARY_KEY,
)
from app.agents.orchestrator import WorkflowOrchestrator, WorkflowRunResult
from app.agents.planning_agent import SCHEDULE_RESULT_KEY
from app.agents.recommendation_agent import RECOMMENDATION_SET_KEY
from app.agents.risk_agent import RISK_REPORT_KEY
from app.agents.scenario_agent import SCENARIO_COMPARISON_KEY
from app.agents.trace import AgentStepTrace
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.domain.models.analytics import KpiSet
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import RiskReport
from app.domain.models.scenario import ScenarioComparison
from app.domain.models.schedule import ScheduleResult
from app.explanation.schema import ExplanationSummary
from app.services import PlanningResult, ResultsStore

logger = get_logger(__name__)


class OrchestrationResult(BaseModel):
    """Full result of a MAF workflow run: trace + artifacts + narration."""

    run_id: str
    business_date: str
    workflow: str
    state: str
    message: str
    completed_agents: list[str] = Field(default_factory=list)
    steps: list[AgentStepTrace] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    persisted: bool = False
    pending_gate: str | None = None

    # Deterministic artifacts (present once the relevant agents have run).
    schedule: ScheduleResult | None = None
    kpis: KpiSet | None = None
    risks: RiskReport | None = None
    recommendations: RecommendationSet | None = None
    scenario_comparison: ScenarioComparison | None = None

    # Explanation (explain-only).
    explanation_summary: ExplanationSummary | None = None
    answer: str | None = None


@dataclass
class _PausedRun:
    """State retained for a paused (awaiting-approval) workflow run."""

    context: WorkflowContext
    pause_after: frozenset[str]
    persist: bool


class MafOrchestrationService:
    """Coordinates a MAF workflow run, HITL approvals, and persistence."""

    def __init__(
        self, orchestrator: WorkflowOrchestrator, results_store: ResultsStore
    ) -> None:
        self._orchestrator = orchestrator
        self._results_store = results_store
        self._paused: dict[str, _PausedRun] = {}

    def run(
        self,
        business_date: str,
        question: str | None = None,
        *,
        persist: bool = True,
        pause_after: list[str] | None = None,
    ) -> OrchestrationResult:
        """Run the workflow, optionally pausing at approval gates."""
        params: dict = {}
        if question:
            params["question"] = question
        context = WorkflowContext(
            run_id=uuid4().hex, business_date=business_date, params=params
        )
        gates = frozenset(pause_after or ())
        run_result = self._orchestrator.run_with_context(context, pause_after=gates)
        return self._finalize(context, run_result, gates, persist)

    def resume(
        self, run_id: str, *, approve: bool, gate: str | None = None
    ) -> OrchestrationResult:
        """Resume (or cancel) a paused run after a planner decision."""
        paused = self._paused.get(run_id)
        if paused is None:
            raise NotFoundError(
                f"No paused workflow run '{run_id}' awaiting approval.",
                details={"run_id": run_id},
            )
        context = paused.context
        resolved_gate = gate or context.pending_gate

        if not approve:
            context.state = WorkflowState.CANCELLED
            self._paused.pop(run_id, None)
            logger.info("Run %s cancelled at gate '%s'.", run_id, resolved_gate)
            cancelled = WorkflowRunResult(
                run_id=run_id,
                business_date=context.business_date,
                workflow=self._orchestrator.workflow.name,
                state=WorkflowState.CANCELLED.value,
                message=f"Rejected at gate '{resolved_gate}'.",
                completed_agents=context.trace.completed_agents(),
                steps=context.trace.steps,
            )
            return self._collect(context, cancelled, persisted=False)

        if resolved_gate:
            context.approvals[resolved_gate] = True
        run_result = self._orchestrator.run_with_context(
            context, pause_after=paused.pause_after
        )
        return self._finalize(context, run_result, paused.pause_after, paused.persist)

    # --- Internal helpers --------------------------------------------------
    def _finalize(
        self,
        context: WorkflowContext,
        run_result: WorkflowRunResult,
        gates: frozenset[str],
        persist: bool,
    ) -> OrchestrationResult:
        """Persist on completion, register on pause, and build the result."""
        if context.state is WorkflowState.AWAITING_APPROVAL:
            self._paused[context.run_id] = _PausedRun(context, gates, persist)
            return self._collect(context, run_result, persisted=False)

        self._paused.pop(context.run_id, None)
        persisted = False
        if context.state is WorkflowState.COMPLETED and persist:
            persisted = self._persist(context)
        return self._collect(context, run_result, persisted=persisted)

    def _persist(self, context: WorkflowContext) -> bool:
        explanation_context = context.shared.get(EXPLANATION_CONTEXT_KEY)
        if explanation_context is None:
            return False
        planning_result = PlanningResult(
            business_date=context.business_date,
            schedule=context.shared.get(SCHEDULE_RESULT_KEY),
            kpis=context.shared.get(KPIS_KEY),
            risks=context.shared.get(RISK_REPORT_KEY),
            recommendations=context.shared.get(RECOMMENDATION_SET_KEY),
            scenario_comparison=context.shared.get(SCENARIO_COMPARISON_KEY),
        )
        self._results_store.save(
            planning_result,
            explanation_context,
            context.shared.get(EXPLANATION_SUMMARY_KEY),
        )
        logger.info("Persisted MAF results for %s.", context.business_date)
        return True

    @staticmethod
    def _collect(
        context: WorkflowContext,
        run_result: WorkflowRunResult,
        *,
        persisted: bool,
    ) -> OrchestrationResult:
        shared = context.shared
        return OrchestrationResult(
            run_id=run_result.run_id,
            business_date=context.business_date,
            workflow=run_result.workflow,
            state=context.state.value,
            message=run_result.message,
            completed_agents=run_result.completed_agents,
            steps=run_result.steps,
            total_duration_ms=run_result.total_duration_ms,
            persisted=persisted,
            pending_gate=context.pending_gate,
            schedule=shared.get(SCHEDULE_RESULT_KEY),
            kpis=shared.get(KPIS_KEY),
            risks=shared.get(RISK_REPORT_KEY),
            recommendations=shared.get(RECOMMENDATION_SET_KEY),
            scenario_comparison=shared.get(SCENARIO_COMPARISON_KEY),
            explanation_summary=shared.get(EXPLANATION_SUMMARY_KEY),
            answer=shared.get(EXPLANATION_ANSWER_KEY),
        )
