"""Scenario endpoint: retrieve the scenario KPI comparison for a business date."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.advisor import (
    PlanningGoalAdvisor,
    ScenarioAdvisor,
    ScenarioRecommendation,
    WeightProposal,
)
from app.advisor.outcome import build_goal_outcome
from app.api.v1.deps import (
    get_goal_advisor,
    get_orchestrator,
    get_results_store,
    get_scenario_advisor,
)
from app.api.v1.schemas import ApplyScenarioRequest, OptimizeGoalRequest
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.enums import ScenarioType
from app.domain.models.scenario import ScenarioComparison
from app.domain.models.schedule import ScheduleResult
from app.optimization import SolverOptions
from app.services import PlanningOrchestrator, ResultsStore

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get(
    "/{business_date}",
    response_model=ScenarioComparison,
    summary="Get scenario comparison",
)
async def get_scenarios(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> ScenarioComparison:
    """Return the persisted scenario comparison for a business date."""
    scenarios = store.load_scenarios(business_date)
    if scenarios is None:
        raise NotFoundError(
            f"No scenario comparison found for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    return scenarios


@router.get(
    "/{business_date}/original",
    summary="Get the fixed original-plan KPIs",
)
async def get_original_plan(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> dict[str, float]:
    """Return the day's write-once ORIGINAL plan KPIs.

    These are captured the first time the pipeline runs for the date and never
    change when scenarios are applied, risks mitigated, or the planner re-runs,
    so the Live Operations page can pin the original plan. Falls back to the
    persisted baseline row for legacy days that predate the snapshot.
    """
    original = store.load_original_kpis(business_date)
    if original is not None:
        return original
    scenarios = store.load_scenarios(business_date)
    if scenarios is not None:
        baseline = next(
            (r for r in scenarios.results if r.is_baseline),
            None,
        )
        if baseline is not None:
            return dict(baseline.kpis)
    raise NotFoundError(
        f"No original plan found for {business_date}; run the pipeline first.",
        details={"business_date": business_date},
    )


@router.post(
    "/{business_date}/apply",
    response_model=ScheduleResult,
    summary="Apply a scenario as the current plan",
)
async def apply_scenario(
    business_date: str,
    request: ApplyScenarioRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> ScheduleResult:
    """Commit the chosen scenario as the committed plan for ``business_date``.

    Re-solves the day using the scenario's transform and persists it as the new
    current plan (replacing the previous one); downstream artifacts are
    recomputed against the applied plan.
    """
    try:
        scenario_type = ScenarioType(request.scenario_type)
    except ValueError as exc:
        raise ValidationError(
            f"Unknown scenario type: {request.scenario_type}.",
            details={"scenario_type": request.scenario_type},
        ) from exc

    options = None
    if request.max_time_seconds is not None:
        options = SolverOptions.from_settings().model_copy(
            update={"max_time_seconds": request.max_time_seconds}
        )
    result = orchestrator.apply_scenario(business_date, scenario_type, options)
    return result.schedule


class OptimizeGoalResponse(BaseModel):
    """Result of planning by a natural-language goal."""

    proposal: WeightProposal
    applied: bool
    kpis: dict[str, float] | None = None
    outcome: str | None = None


@router.post(
    "/{business_date}/optimize-goal",
    response_model=OptimizeGoalResponse,
    summary="Plan by a natural-language goal",
)
async def optimize_goal(
    business_date: str,
    request: OptimizeGoalRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
    advisor: Annotated[PlanningGoalAdvisor, Depends(get_goal_advisor)],
) -> OptimizeGoalResponse:
    """Translate a planner's goal into an objective weighting and re-solve.

    The LLM advisor only chooses *how to weight* a fixed set of objective terms;
    the validated weighting is handed to the deterministic CP-SAT solver, which
    produces the actual schedule. When ``apply`` is false the proposed weighting
    is returned as a preview without committing a new plan.
    """
    proposal = advisor.propose_weights(request.goal)
    # Only commit a re-plan when the assistant genuinely understood the goal and
    # derived an objective from it. Greetings, off-topic text, an unmappable
    # goal, or an unavailable assistant all return a conversational reply
    # (proposal.usable is False) WITHOUT throwing a default plan at the user.
    should_apply = request.apply and proposal.usable
    if not should_apply:
        return OptimizeGoalResponse(proposal=proposal, applied=False)

    options = None
    if request.max_time_seconds is not None:
        options = SolverOptions.from_settings().model_copy(
            update={"max_time_seconds": request.max_time_seconds}
        )
    result = orchestrator.apply_planning_goal(
        business_date,
        proposal.weights,
        proposal.goal,
        strategy=proposal.strategy,
        options=options,
    )
    after = dict(result.kpis.metrics) | {
        "on_time_delivery_rate": float(result.kpis.on_time_delivery_rate or 0.0),
        "average_machine_utilization": float(
            result.kpis.average_machine_utilization or 0.0
        ),
        "total_tardiness_minutes": float(result.kpis.total_tardiness_minutes or 0),
    }
    # Grounded outcome reasoning: did the goal's intent actually land, and if not,
    # why (e.g. on-time delivery is capped by materials / due dates)? Compared
    # against the day's fixed original plan and the scenario ceiling.
    store = orchestrator.store
    before = store.load_original_kpis(business_date) or {}
    outcome = build_goal_outcome(
        proposal.weights, before, after, store.load_scenarios(business_date)
    )
    return OptimizeGoalResponse(
        proposal=proposal,
        applied=True,
        kpis=after,
        outcome=outcome or None,
    )


@router.post(
    "/{business_date}/recommend",
    response_model=ScenarioRecommendation,
    summary="Recommend which scenario to commit",
)
async def recommend_scenario(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
    advisor: Annotated[ScenarioAdvisor, Depends(get_scenario_advisor)],
) -> ScenarioRecommendation:
    """Recommend the best scenario to commit, grounded on the solved comparison.

    Read-only: it reasons over the persisted scenario KPIs/deltas and changes
    nothing. Falls back to a deterministic pick when the assistant is offline.
    """
    scenarios = store.load_scenarios(business_date)
    if scenarios is None:
        raise NotFoundError(
            f"No scenario comparison found for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    return advisor.recommend(scenarios)
