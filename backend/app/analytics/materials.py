"""Materials availability analytics.

Builds a full materials/inventory availability report from the day's snapshot:
on-hand vs allocated balances, the net available, and any shortage against the
reorder point or safety stock. Powers the Materials tab and its place-order
action. Purely derived from the snapshot; never mutates state.
"""

from __future__ import annotations

from pydantic import Field

from app.domain.models.base import FrozenDomainModel
from app.domain.models.factory_state import FactoryState


class MaterialLine(FrozenDomainModel):
    """Availability and shortage for a single material/product."""

    product_id: str = Field(..., description="Material/product identifier.")
    name: str | None = Field(default=None, description="Human-readable name, if known.")
    on_hand: float = Field(..., description="Physical quantity in stock.")
    allocated: float = Field(..., description="Quantity reserved for existing orders.")
    net_available: float = Field(..., description="On-hand minus allocated.")
    safety_stock: float = Field(..., description="Minimum stock to keep on hand.")
    reorder_point: float = Field(..., description="Level that triggers replenishment.")
    shortage: float = Field(
        ..., description="Deficit below the reorder point (0 when sufficient)."
    )
    below_reorder: bool = Field(..., description="Net available is below reorder point.")
    below_safety: bool = Field(..., description="Net available is below safety stock.")


class MaterialsReport(FrozenDomainModel):
    """Full materials availability report for a business date."""

    business_date: str = Field(..., description="Day the report applies to.")
    total: int = Field(..., description="Number of materials tracked.")
    below_reorder: int = Field(..., description="Count below their reorder point.")
    below_safety: int = Field(..., description="Count below their safety stock.")
    lines: list[MaterialLine] = Field(default_factory=list)


def build_materials_report(state: FactoryState) -> MaterialsReport:
    """Compute the materials availability report from a factory snapshot."""
    names: dict[str, str] = {}
    for product in getattr(state, "products", []) or []:
        pid = getattr(product, "product_id", None)
        name = getattr(product, "name", None)
        if pid and name:
            names[pid] = name

    lines: list[MaterialLine] = []
    below_reorder = 0
    below_safety = 0
    for item in state.inventory:
        net = round(item.on_hand - item.allocated, 2)
        is_below_reorder = item.reorder_point > 0 and net < item.reorder_point
        is_below_safety = item.safety_stock > 0 and net < item.safety_stock
        shortage = round(max(0.0, item.reorder_point - net), 2)
        if is_below_reorder:
            below_reorder += 1
        if is_below_safety:
            below_safety += 1
        lines.append(
            MaterialLine(
                product_id=item.product_id,
                name=names.get(item.product_id),
                on_hand=round(item.on_hand, 2),
                allocated=round(item.allocated, 2),
                net_available=net,
                safety_stock=item.safety_stock,
                reorder_point=item.reorder_point,
                shortage=shortage,
                below_reorder=is_below_reorder,
                below_safety=is_below_safety,
            )
        )

    # Most critical first: below safety, then below reorder, then by shortage.
    lines.sort(
        key=lambda ln: (not ln.below_safety, not ln.below_reorder, -ln.shortage)
    )

    return MaterialsReport(
        business_date=state.business_date,
        total=len(lines),
        below_reorder=below_reorder,
        below_safety=below_safety,
        lines=lines,
    )
