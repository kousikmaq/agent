"""Analytics / KPI DTOs produced by the analytics engine (later phase)."""

from __future__ import annotations

from pydantic import Field

from app.domain.models.base import FrozenDomainModel


class KpiSet(FrozenDomainModel):
    """Key performance indicators computed from a schedule.

    Values are stored in a flexible map so new KPIs can be added without schema
    changes, while the most common headline metrics are surfaced as typed
    convenience fields.
    """

    business_date: str = Field(..., description="Day the KPIs apply to (YYYY-MM-DD).")
    on_time_delivery_rate: float | None = Field(
        default=None, ge=0, le=1, description="Fraction of orders completed by due date."
    )
    average_machine_utilization: float | None = Field(
        default=None, ge=0, le=1, description="Mean machine utilisation (0-1)."
    )
    total_tardiness_minutes: int | None = Field(
        default=None, ge=0, description="Sum of lateness across all orders."
    )
    work_in_progress: int | None = Field(
        default=None, ge=0, description="Count of orders in progress."
    )
    metrics: dict[str, float] = Field(
        default_factory=dict, description="Additional named KPI values."
    )
