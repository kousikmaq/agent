"""Scenario endpoint: retrieve the scenario KPI comparison for a business date."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_orchestrator, get_results_store
from app.api.v1.schemas import ApplyScenarioRequest
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
