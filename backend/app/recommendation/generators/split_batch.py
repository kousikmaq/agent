"""Generator: split a production batch.

Addresses delayed orders and capacity shortages by splitting large orders into
smaller batches that can run in parallel across eligible machines, shortening
the critical path.
"""

from __future__ import annotations

from app.domain.enums import (
    RecommendationAction,
    RecommendationFeasibility,
    RiskType,
)
from app.recommendation.result import (
    RecommendationBuilder,
    RecommendationContext,
    priority_from_severity,
)

_RELEVANT = {RiskType.DELAYED_ORDER, RiskType.CAPACITY_SHORTAGE}
# Only orders at or above this quantity are worth splitting.
_MIN_SPLIT_QUANTITY = 2


def generate(ctx: RecommendationContext, builder: RecommendationBuilder) -> None:
    """Propose batch splits for large orders behind delays / capacity shortages."""
    for risk in ctx.risk_report.risks:
        if risk.risk_type not in _RELEVANT:
            continue
        for order_id in risk.affected_entities.get("order_ids", []):
            order = ctx.order_by_id.get(order_id)
            if order is None or order.quantity < _MIN_SPLIT_QUANTITY:
                continue
            half = order.quantity // 2
            builder.add(
                action=RecommendationAction.SPLIT_BATCH,
                addresses_risk_ids=[risk.risk_id],
                title=f"Split order {order_id} into parallel batches",
                description=(
                    f"Split order {order_id} (quantity {order.quantity}) into batches "
                    f"of ~{half} to run in parallel on eligible machines and shorten "
                    "its critical path."
                ),
                target_entities={"order_ids": [order_id]},
                expected_impact={
                    "original_quantity": order.quantity,
                    "suggested_batch_quantity": half,
                },
                feasibility=RecommendationFeasibility.FEASIBLE,
                priority=priority_from_severity(risk.severity),
            )
