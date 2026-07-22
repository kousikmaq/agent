"""Customer master data."""

from __future__ import annotations

from pydantic import Field

from app.domain.enums import CustomerTier
from app.domain.models.base import DomainModel


class Customer(DomainModel):
    """A customer that places production orders.

    The ``tier`` and ``sla_days`` drive deterministic priority weighting in the
    business-rules and optimization layers.
    """

    customer_id: str = Field(..., description="Unique customer identifier.")
    name: str = Field(..., description="Customer display name.")
    tier: CustomerTier = Field(
        default=CustomerTier.STANDARD,
        description="Priority tier used for order weighting.",
    )
    sla_days: int = Field(
        default=0,
        ge=0,
        description="Contractual service-level lead time in days.",
    )
    country: str | None = Field(
        default=None, description="Customer country / region code."
    )
