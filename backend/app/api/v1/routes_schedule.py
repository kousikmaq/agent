"""Schedule endpoints: run the pipeline and retrieve the generated schedule."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.v1.deps import get_orchestrator, get_results_store
from app.api.v1.schemas import RunScheduleRequest
from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.domain.models.schedule import ScheduleResult
from app.optimization import SolverOptions
from app.services import PlanningOrchestrator, ResultsStore

router = APIRouter(prefix="/schedule", tags=["schedule"])


class AutoRemediateRequest(BaseModel):
    """Request body to run autonomous remediation for a business date."""

    business_date: str = Field(..., description="Business date (YYYY-MM-DD).")
    priority_max: int | None = Field(
        default=None,
        description="Highest display priority (0=most urgent) that triggers a "
        "re-plan; defaults to the configured value.",
    )
    notify: bool | None = Field(
        default=None,
        description="Email a risk + replan summary; defaults to the configured value.",
    )
    max_time_seconds: float | None = Field(
        default=None, description="Optional solver time budget for the re-plan."
    )


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


@router.post(
    "/auto-remediate",
    summary="Autonomously re-plan around high-priority late orders",
)
async def auto_remediate(
    request: AutoRemediateRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> dict:
    """Detect top-priority orders running late and auto-re-plan to prioritise them.

    A reversible action recorded in the modification log; optionally emails a
    risk + replan summary. Returns a summary of what was done (or a no-op when
    nothing needs attention).
    """
    settings = get_settings()
    options = None
    if request.max_time_seconds is not None:
        options = SolverOptions.from_settings().model_copy(
            update={"max_time_seconds": request.max_time_seconds}
        )
    priority_max = (
        request.priority_max
        if request.priority_max is not None
        else settings.auto_replan_priority_max
    )
    notify = (
        request.notify if request.notify is not None else settings.auto_notify_email
    )
    return orchestrator.auto_remediate(
        request.business_date,
        priority_max=priority_max,
        notify=notify,
        options=options,
    )


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
