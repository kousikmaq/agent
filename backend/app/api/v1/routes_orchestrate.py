"""Orchestration endpoint (MAF).

Runs the full MAF agent workflow, returns every deterministic artifact plus the
explain-only narration, and persists the results to ``outputs/<date>/`` (so the
existing schedule/analytics/risks/recommendations/scenarios endpoints and the
frontend work unchanged).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.registration import get_maf_service
from app.agents.service import MafOrchestrationService, OrchestrationResult

router = APIRouter(prefix="/orchestrate", tags=["orchestrate"])


class OrchestrateRunRequest(BaseModel):
    """Request body to run the MAF planning workflow for a date."""

    business_date: str = Field(..., description="Business date to plan (YYYY-MM-DD).")
    question: str | None = Field(
        default=None,
        description="Optional planner question for the explain-only assistant.",
    )
    persist: bool = Field(
        default=True, description="Persist results to outputs/<date>/."
    )
    pause_after: list[str] | None = Field(
        default=None,
        description="Agent names after which to pause for approval (HITL gates).",
    )


class OrchestrateResumeRequest(BaseModel):
    """Request body to resume (or reject) a paused workflow run."""

    run_id: str = Field(..., description="The paused run identifier.")
    approve: bool = Field(..., description="Approve to continue, or reject to cancel.")
    gate: str | None = Field(
        default=None, description="The gate being decided (defaults to the pending gate)."
    )


def _service() -> MafOrchestrationService:
    return get_maf_service()


@router.post("/run", response_model=OrchestrationResult, summary="Run the MAF workflow")
async def run_workflow(
    request: OrchestrateRunRequest,
    service: Annotated[MafOrchestrationService, Depends(_service)],
) -> OrchestrationResult:
    """Run the orchestrated agent workflow end to end.

    Returns the execution trace, all deterministic artifacts (schedule, KPIs,
    risks, recommendations, scenario comparison), the curated explanation
    summary, and - when a question is supplied - a grounded, explain-only answer.
    When ``pause_after`` gates are given, the run stops with state
    ``AWAITING_APPROVAL`` and a ``pending_gate`` for approval via ``/resume``.
    """
    return service.run(
        request.business_date,
        request.question,
        persist=request.persist,
        pause_after=request.pause_after,
    )


@router.post(
    "/resume", response_model=OrchestrationResult, summary="Resume a paused run"
)
async def resume_workflow(
    request: OrchestrateResumeRequest,
    service: Annotated[MafOrchestrationService, Depends(_service)],
) -> OrchestrationResult:
    """Approve (continue) or reject (cancel) a workflow paused at an approval gate."""
    return service.resume(request.run_id, approve=request.approve, gate=request.gate)
