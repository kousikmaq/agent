"""Detector: material shortage.

Performs a plant-level material balance: explodes every schedulable order's bill
of materials into component demand and compares it with available supply
(net on-hand plus all inbound purchase orders). Components whose demand exceeds
supply are flagged, along with the orders that consume them.
"""

from __future__ import annotations

import math

from app.domain.enums import OrderStatus, PurchaseOrderStatus, RiskSeverity, RiskType
from app.risk.result import RiskBuilder, RiskContext

_SCHEDULABLE = {OrderStatus.PLANNED, OrderStatus.RELEASED, OrderStatus.IN_PROGRESS}
_INBOUND = {
    PurchaseOrderStatus.OPEN,
    PurchaseOrderStatus.CONFIRMED,
    PurchaseOrderStatus.IN_TRANSIT,
    PurchaseOrderStatus.DELAYED,
}


def _severity(coverage: float) -> RiskSeverity:
    """Severity from the fraction of demand that supply can cover (0-1)."""
    if coverage <= 0.25:
        return RiskSeverity.CRITICAL
    if coverage <= 0.5:
        return RiskSeverity.HIGH
    return RiskSeverity.MEDIUM


def detect(ctx: RiskContext, builder: RiskBuilder) -> None:
    """Emit a MATERIAL_SHORTAGE risk per under-supplied component."""
    state = ctx.state
    inventory_by_product = {item.product_id: item for item in state.inventory}

    # Component demand + consuming orders.
    demand: dict[str, float] = {}
    consumers: dict[str, set[str]] = {}
    boms_by_parent: dict[str, list] = {}
    for line in state.boms:
        boms_by_parent.setdefault(line.parent_product_id, []).append(line)

    for order in state.production_orders:
        if order.status not in _SCHEDULABLE:
            continue
        for line in boms_by_parent.get(order.product_id, []):
            required = math.ceil(order.quantity * line.quantity_per * (1 + line.scrap_factor))
            demand[line.component_product_id] = (
                demand.get(line.component_product_id, 0.0) + required
            )
            consumers.setdefault(line.component_product_id, set()).add(order.order_id)

    # Inbound supply per component.
    inbound: dict[str, float] = {}
    for po in state.purchase_orders:
        if po.status in _INBOUND:
            inbound[po.product_id] = inbound.get(po.product_id, 0.0) + po.quantity

    for component, required in demand.items():
        item = inventory_by_product.get(component)
        net_on_hand = (item.on_hand - item.allocated) if item else 0.0
        supply = net_on_hand + inbound.get(component, 0.0)
        if supply >= required:
            continue
        coverage = supply / required if required > 0 else 1.0
        builder.add(
            risk_type=RiskType.MATERIAL_SHORTAGE,
            severity=_severity(coverage),
            title=f"Material shortage for {component} ({coverage:.0%} covered)",
            description=(
                f"Component {component} has demand of {required:.0f} against supply "
                f"of {supply:.0f} (net on-hand {net_on_hand:.0f} + inbound "
                f"{inbound.get(component, 0.0):.0f})."
            ),
            affected_entities={
                "product_ids": [component],
                "order_ids": sorted(consumers.get(component, set())),
            },
            evidence={
                "required": round(required, 2),
                "net_on_hand": round(net_on_hand, 2),
                "inbound": round(inbound.get(component, 0.0), 2),
                "shortfall": round(required - supply, 2),
                "coverage_ratio": round(coverage, 4),
            },
        )
