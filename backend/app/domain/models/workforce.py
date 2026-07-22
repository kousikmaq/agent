"""Workforce master data and worker skills."""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from app.domain.enums import SkillProficiency, WorkerAvailabilityStatus
from app.domain.models.base import DomainModel


class WorkerSkill(DomainModel):
    """A skill a worker holds, with a proficiency level."""

    worker_id: str = Field(..., description="Worker who holds the skill.")
    skill: str = Field(..., description="Skill code (matches Operation.required_skill).")
    proficiency: SkillProficiency = Field(
        default=SkillProficiency.INTERMEDIATE,
        description="Worker's proficiency in the skill.",
    )


class Worker(DomainModel):
    """A member of the workforce assignable to operations."""

    worker_id: str = Field(..., description="Unique worker identifier.")
    name: str = Field(..., description="Worker display name.")
    home_shift_id: str | None = Field(
        default=None, description="Default shift the worker is assigned to."
    )
    max_regular_minutes_per_day: int = Field(
        default=480,
        ge=0,
        description="Regular working minutes per day before overtime.",
    )
    max_overtime_minutes_per_day: int = Field(
        default=120,
        ge=0,
        description="Maximum additional overtime minutes permitted per day.",
    )
    overtime_allowed: bool = Field(
        default=True, description="Whether overtime may be scheduled for this worker."
    )


class WorkerAvailability(DomainModel):
    """A dated availability record for a worker (leave, sickness, training)."""

    worker_id: str = Field(..., description="Worker the record applies to.")
    day: date = Field(..., description="Calendar day of the record.")
    status: WorkerAvailabilityStatus = Field(
        default=WorkerAvailabilityStatus.AVAILABLE,
        description="Availability status on the day.",
    )
    shift_id: str | None = Field(
        default=None,
        description="Shift worked on the day (may differ from home shift on swaps).",
    )
    approved_overtime_minutes: int = Field(
        default=0,
        ge=0,
        description="Overtime minutes approved for the worker on the day.",
    )

    @model_validator(mode="after")
    def _validate_overtime(self) -> "WorkerAvailability":
        """Approved overtime is only meaningful for available workers."""
        if (
            self.status != WorkerAvailabilityStatus.AVAILABLE
            and self.approved_overtime_minutes > 0
        ):
            raise ValueError(
                f"Worker {self.worker_id}: overtime cannot be approved while "
                f"status is {self.status}."
            )
        return self
