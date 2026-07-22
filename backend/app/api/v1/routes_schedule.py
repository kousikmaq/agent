"""Schedule endpoints: run the pipeline and retrieve the generated schedule."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_orchestrator, get_results_store
from app.api.v1.schemas import RunScheduleRequest
from app.core.exceptions import NotFoundError
from app.domain.models.schedule import ScheduleResult
from app.optimization import SolverOptions
from app.services import PlanningOrchestrator, ResultsStore

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("/run", response_model=ScheduleResult, summary="Run the planning pipeline")
async def run_schedule(
    request: RunScheduleRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> ScheduleResult:
    """Run (or re-run) the full deterministic pipeline and return the schedule.

    Also computes and persists analytics, risks, recommendations, scenarios, and
    the explanation context, retrievable via their respective endpoints.
    """
    options = None
    if request.max_time_seconds is not None:
        options = SolverOptions.from_settings().model_copy(
            update={"max_time_seconds": request.max_time_seconds}
        )
    result = orchestrator.get_or_run(
        request.business_date, options, force=request.force
    )
    return result.schedule


@router.get("/{business_date}", response_model=ScheduleResult, summary="Get a schedule")
async def get_schedule(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> ScheduleResult:
    """Return the persisted schedule for a business date."""
    schedule = store.load_schedule(business_date)
    if schedule is None:
        raise NotFoundError(
            f"No schedule found for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    return schedule
