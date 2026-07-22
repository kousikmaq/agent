"""Product master data."""

from __future__ import annotations

from pydantic import Field

from app.domain.enums import UnitOfMeasure
from app.domain.models.base import DomainModel


class Product(DomainModel):
    """A finished good or intermediate/component product.

    A product is manufactured according to a :class:`Routing` (referenced by
    ``routing_id``) and may itself appear as a component in another product's
    bill of materials.
    """

    product_id: str = Field(..., description="Unique product identifier / SKU.")
    name: str = Field(..., description="Product display name.")
    uom: UnitOfMeasure = Field(
        default=UnitOfMeasure.EACH, description="Base unit of measure."
    )
    routing_id: str | None = Field(
        default=None,
        description="Routing used to manufacture this product; None if purchased.",
    )
    standard_cost: float = Field(
        default=0.0, ge=0, description="Standard unit cost."
    )
    is_purchased: bool = Field(
        default=False,
        description="True for bought-in materials (no routing / not produced).",
    )
