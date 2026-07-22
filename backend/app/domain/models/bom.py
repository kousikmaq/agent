"""Bill of Materials (BOM) data."""

from __future__ import annotations

from pydantic import Field, model_validator

from app.domain.models.base import DomainModel


class BomLine(DomainModel):
    """A single parent-component relationship in a bill of materials.

    A product's full BOM is the collection of lines sharing the same
    ``parent_product_id``.
    """

    parent_product_id: str = Field(..., description="Product being assembled.")
    component_product_id: str = Field(..., description="Component/material consumed.")
    quantity_per: float = Field(
        ..., gt=0, description="Component quantity required per parent unit."
    )
    scrap_factor: float = Field(
        default=0.0,
        ge=0,
        lt=1,
        description="Expected fractional scrap (0.05 = 5% extra consumed).",
    )

    @model_validator(mode="after")
    def _validate_not_self_referencing(self) -> "BomLine":
        """A product cannot be a component of itself."""
        if self.parent_product_id == self.component_product_id:
            raise ValueError(
                f"BOM line for {self.parent_product_id} cannot reference itself as "
                "a component."
            )
        return self
