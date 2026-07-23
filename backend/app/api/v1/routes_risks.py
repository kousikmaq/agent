"""Risk endpoint: retrieve the detected risk report for a business date."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_orchestrator, get_results_store
from app.api.v1.schemas import (
    ApplyFixesRequest,
    ApplyFixRequest,
    MitigateOrdersRequest,
    ReplanPrioritiesRequest,
)
from app.core.exceptions import NotFoundError
from app.domain.models.modifications import PlanModifications
from app.domain.models.risk import RiskReport
from app.domain.models.schedule import ScheduleResult
from app.optimization import SolverOptions
from app.services import PlanningOrchestrator, ResultsStore

router = APIRouter(prefix="/risks", tags=["risks"])


@router.get("/{business_date}", response_model=RiskReport, summary="Get risks")
async def get_risks(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> RiskReport:
    """Return the persisted risk report for a business date."""
    risks = store.load_risks(business_date)
    if risks is None:
        raise NotFoundError(
            f"No risk report found for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    return risks


@router.get(
    "/{business_date}/modifications",
    response_model=PlanModifications,
    summary="Get the plan modification log (before/after KPIs)",
)
async def get_modifications(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> PlanModifications:
    """Return the applied-modification log for a business date."""
    mods = store.load_modifications(business_date)
    if mods is None:
        raise NotFoundError(
            f"No modification log for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    return mods


@router.post(
    "/{business_date}/mitigate-priority",
    response_model=ScheduleResult,
    summary="Raise the priority of delayed orders and re-solve",
)
async def mitigate_priority(
    business_date: str,
    request: MitigateOrdersRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> ScheduleResult:
    """Mitigate a delayed-order risk by raising the affected orders' priority.

    Re-solves the day with the boosted priorities and persists the new plan
    (replacing the previous one); downstream artifacts are recomputed against
    the re-solved plan.
    """
    options = None
    if request.max_time_seconds is not None:
        options = SolverOptions.from_settings().model_copy(
            update={"max_time_seconds": request.max_time_seconds}
        )
    result = orchestrator.apply_order_priority(
        business_date, request.order_ids, request.priority, options
    )
    return result.schedule


@router.post(
    "/{business_date}/replan-priorities",
    response_model=ScheduleResult,
    summary="Set per-order priorities and re-solve the day",
)
async def replan_priorities(
    business_date: str,
    request: ReplanPrioritiesRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> ScheduleResult:
    """Assign each order its own priority and re-solve the day once.

    Lets a planner raise some orders and lower others in a single re-plan;
    persists the new plan (replacing the previous one) and recomputes the
    downstream artifacts against it.
    """
    options = None
    if request.max_time_seconds is not None:
        options = SolverOptions.from_settings().model_copy(
            update={"max_time_seconds": request.max_time_seconds}
        )
    result = orchestrator.apply_order_priorities(
        business_date, request.priorities, options
    )
    return result.schedule


@router.post(
    "/{business_date}/apply-fix",
    response_model=ScheduleResult,
    summary="Apply a recommended fix action and re-solve",
)
async def apply_fix(
    business_date: str,
    request: ApplyFixRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> ScheduleResult:
    """Mitigate a risk by applying its recommended fix and re-planning.

    Applies the action's state transform (alternate machines, add shift,
    reschedule maintenance, free up workers, replenish materials, …), re-solves
    the day, and persists the new plan (replacing the previous one); downstream
    artifacts are recomputed against the re-solved plan.
    """
    options = None
    if request.max_time_seconds is not None:
        options = SolverOptions.from_settings().model_copy(
            update={"max_time_seconds": request.max_time_seconds}
        )
    result = orchestrator.apply_recommendation_action(
        business_date, request.action, request.targets, options
    )
    return result.schedule


@router.post(
    "/{business_date}/apply-fixes",
    response_model=ScheduleResult,
    summary="Apply several fixes (priority + actions) in one re-solve",
)
async def apply_fixes(
    business_date: str,
    request: ApplyFixesRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> ScheduleResult:
    """Apply many selected fixes at once and re-plan a single time.

    Raises the priority of the given orders and applies every fix action, then
    re-solves the day once and persists the new plan — so bulk mitigation of a
    filtered risk selection needs only one solve.
    """
    options = None
    if request.max_time_seconds is not None:
        options = SolverOptions.from_settings().model_copy(
            update={"max_time_seconds": request.max_time_seconds}
        )
    result = orchestrator.apply_fixes(
        business_date,
        request.order_ids,
        request.priority,
        [(a.action, a.targets) for a in request.actions],
        options,
    )
    return result.schedule

