"""Schedule result DTOs produced by the optimization engine.

These are output data structures only; the CP-SAT model that populates them is
implemented in the optimization phase.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.enums import SolverStatus
from app.domain.models.base import FrozenDomainModel


class ScheduledOperation(FrozenDomainModel):
    """A single operation assignment in a generated schedule."""

    order_id: str = Field(..., description="Production order the operation serves.")
    operation_id: str = Field(..., description="Operation that was scheduled.")
    machine_id: str = Field(..., description="Machine assigned to the operation.")
    worker_id: str | None = Field(
        default=None, description="Worker assigned to the operation, if any."
    )
    start: datetime = Field(..., description="Scheduled start time.")
    end: datetime = Field(..., description="Scheduled end time.")


class ScheduleResult(FrozenDomainModel):
    """The full deterministic schedule for a production day."""

    business_date: str = Field(..., description="Day the schedule applies to (YYYY-MM-DD).")
    status: SolverStatus = Field(..., description="Solver outcome.")
    scheduled_operations: list[ScheduledOperation] = Field(
        default_factory=list, description="All operation assignments."
    )
    makespan_minutes: int | None = Field(
        default=None, ge=0, description="Total schedule span in minutes."
    )
    objective_value: float | None = Field(
        default=None, description="Value of the optimisation objective."
    )
    solve_time_seconds: float | None = Field(
        default=None, ge=0, description="Wall-clock solve time."
    )
