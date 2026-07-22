"""Shift definitions and per-day shift calendar."""

from __future__ import annotations

from datetime import date, time

from pydantic import Field, model_validator

from app.domain.enums import ShiftType
from app.domain.models.base import DomainModel


class Shift(DomainModel):
    """A named recurring shift template."""

    shift_id: str = Field(..., description="Unique shift identifier.")
    shift_type: ShiftType = Field(..., description="Standard shift window type.")
    start_time: time = Field(..., description="Shift start time of day.")
    end_time: time = Field(..., description="Shift end time of day.")
    break_minutes: int = Field(
        default=0, ge=0, description="Unpaid break minutes within the shift."
    )


class ShiftCalendar(DomainModel):
    """A concrete instance of a shift on a specific day.

    Overnight shifts are permitted (``end_time`` <= ``start_time``); the
    ``crosses_midnight`` flag makes the intent explicit for downstream phases.
    """

    shift_id: str = Field(..., description="Shift this calendar entry instantiates.")
    day: date = Field(..., description="Calendar day the shift runs on.")
    start_time: time = Field(..., description="Effective start time on the day.")
    end_time: time = Field(..., description="Effective end time on the day.")
    break_minutes: int = Field(
        default=0, ge=0, description="Unpaid break minutes within the shift."
    )
    crosses_midnight: bool = Field(
        default=False, description="True when the shift extends past midnight."
    )

    @model_validator(mode="after")
    def _validate_times(self) -> "ShiftCalendar":
        """Non-overnight shifts must end after they start."""
        if not self.crosses_midnight and self.end_time <= self.start_time:
            raise ValueError(
                f"Shift {self.shift_id} on {self.day}: end_time must be after "
                f"start_time unless crosses_midnight is set."
            )
        return self
