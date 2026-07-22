"""Production order data.

Production orders are the primary demand signal consumed by the optimization
engine. They evolve day to day (new orders, cancellations, priority changes)
via the stateful simulator.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from app.domain.enums import OrderStatus
from app.domain.models.base import DomainModel


class ProductionOrder(DomainModel):
    """A demand for a quantity of a product by a due date."""

    order_id: str = Field(..., description="Unique production order identifier.")
    product_id: str = Field(..., description="Product to be manufactured.")
    customer_id: str | None = Field(
        default=None, description="Customer the order belongs to, if any."
    )
    quantity: int = Field(..., gt=0, description="Quantity to produce (units).")
    release_date: date = Field(
        ..., description="Earliest date production may start."
    )
    due_date: date = Field(..., description="Date the order is required by.")
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Order priority (1 = lowest, 10 = highest).",
    )
    status: OrderStatus = Field(
        default=OrderStatus.RELEASED, description="Current order status."
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> "ProductionOrder":
        """Due date must not precede the release date."""
        if self.due_date < self.release_date:
            raise ValueError(
                f"Order {self.order_id}: due_date ({self.due_date}) cannot precede "
                f"release_date ({self.release_date})."
            )
        return self
