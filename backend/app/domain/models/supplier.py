"""Supplier master data."""

from __future__ import annotations

from pydantic import Field

from app.domain.models.base import DomainModel


class Supplier(DomainModel):
    """A vendor that supplies purchased materials."""

    supplier_id: str = Field(..., description="Unique supplier identifier.")
    name: str = Field(..., description="Supplier display name.")
    lead_time_days: int = Field(
        default=0, ge=0, description="Nominal replenishment lead time in days."
    )
    reliability_score: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description="On-time delivery reliability (0-1, 1 = fully reliable).",
    )
    country: str | None = Field(
        default=None, description="Supplier country / region code."
    )
