"""Plant calendar defining working and non-working days."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.domain.models.base import DomainModel


class PlantCalendar(DomainModel):
    """A single calendar day's working status for the plant."""

    day: date = Field(..., description="Calendar day.")
    is_working_day: bool = Field(
        default=True, description="Whether the plant operates on this day."
    )
    holiday_name: str | None = Field(
        default=None, description="Holiday name when the plant is closed."
    )
