"""Inventory master data with safety-stock tracking."""

from __future__ import annotations

from pydantic import Field, model_validator

from app.domain.models.base import DomainModel


class InventoryItem(DomainModel):
    """On-hand and allocated stock for a product/material.

    ``available`` (on_hand - allocated) is derived by later phases; only the
    raw balances are stored here.
    """

    product_id: str = Field(..., description="Product/material the stock is of.")
    on_hand: float = Field(default=0.0, ge=0, description="Physical quantity in stock.")
    allocated: float = Field(
        default=0.0, ge=0, description="Quantity reserved for existing orders."
    )
    safety_stock: float = Field(
        default=0.0, ge=0, description="Minimum stock to keep on hand."
    )
    reorder_point: float = Field(
        default=0.0, ge=0, description="Level at which replenishment is triggered."
    )

    @model_validator(mode="after")
    def _validate_allocation(self) -> "InventoryItem":
        """Allocated quantity cannot exceed physical stock on hand."""
        if self.allocated > self.on_hand:
            raise ValueError(
                f"Inventory {self.product_id}: allocated ({self.allocated}) cannot "
                f"exceed on_hand ({self.on_hand})."
            )
        return self
