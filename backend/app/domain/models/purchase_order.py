"""Purchase order data for material replenishment."""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from app.domain.enums import PurchaseOrderStatus
from app.domain.models.base import DomainModel


class PurchaseOrder(DomainModel):
    """An inbound order for a purchased material from a supplier.

    Expected-arrival dates shift day to day as suppliers confirm, delay, or
    deliver (driven by the stateful simulator).
    """

    po_id: str = Field(..., description="Unique purchase order identifier.")
    supplier_id: str = Field(..., description="Supplier fulfilling the order.")
    product_id: str = Field(..., description="Material being replenished.")
    quantity: float = Field(..., gt=0, description="Ordered quantity.")
    order_date: date = Field(..., description="Date the PO was raised.")
    expected_arrival: date = Field(
        ..., description="Current expected goods-receipt date."
    )
    status: PurchaseOrderStatus = Field(
        default=PurchaseOrderStatus.OPEN, description="Current PO status."
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> "PurchaseOrder":
        """Expected arrival cannot precede the order date."""
        if self.expected_arrival < self.order_date:
            raise ValueError(
                f"PO {self.po_id}: expected_arrival ({self.expected_arrival}) cannot "
                f"precede order_date ({self.order_date})."
            )
        return self
