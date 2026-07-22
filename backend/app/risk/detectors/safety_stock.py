"""Detector: inventory below safety stock.

Flags inventory items whose net available quantity (on-hand minus allocated)
has fallen below the safety-stock level, or below the reorder point. Severity
scales with how deep the breach is.
"""

from __future__ import annotations

from app.domain.enums import RiskSeverity, RiskType
from app.risk.result import RiskBuilder, RiskContext


def detect(ctx: RiskContext, builder: RiskBuilder) -> None:
    """Emit an INVENTORY_BELOW_SAFETY_STOCK risk per breached item."""
    for item in ctx.state.inventory:
        net = item.on_hand - item.allocated

        if item.safety_stock > 0 and net < item.safety_stock:
            if net <= 0:
                severity = RiskSeverity.CRITICAL
            elif net < item.safety_stock * 0.5:
                severity = RiskSeverity.HIGH
            else:
                severity = RiskSeverity.MEDIUM
            builder.add(
                risk_type=RiskType.INVENTORY_BELOW_SAFETY_STOCK,
                severity=severity,
                title=f"{item.product_id} below safety stock",
                description=(
                    f"Net available {net:.0f} of {item.product_id} is below the "
                    f"safety stock of {item.safety_stock:.0f}."
                ),
                affected_entities={"product_ids": [item.product_id]},
                evidence={
                    "on_hand": item.on_hand,
                    "allocated": item.allocated,
                    "net_available": round(net, 2),
                    "safety_stock": item.safety_stock,
                    "reorder_point": item.reorder_point,
                },
            )
        elif item.reorder_point > 0 and net < item.reorder_point:
            # Above safety stock but below reorder point - low-severity signal.
            builder.add(
                risk_type=RiskType.INVENTORY_BELOW_SAFETY_STOCK,
                severity=RiskSeverity.LOW,
                title=f"{item.product_id} below reorder point",
                description=(
                    f"Net available {net:.0f} of {item.product_id} is below the "
                    f"reorder point of {item.reorder_point:.0f}."
                ),
                affected_entities={"product_ids": [item.product_id]},
                evidence={
                    "net_available": round(net, 2),
                    "reorder_point": item.reorder_point,
                    "safety_stock": item.safety_stock,
                },
            )
