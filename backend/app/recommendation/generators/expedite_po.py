"""Generator: expedite purchase orders / replenish from an alternate supplier.

Addresses material shortages and safety-stock breaches. If an inbound purchase
order exists for the component, propose expediting it; otherwise, if an
alternate supplier is available, propose raising a replenishment order there.
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

_RELEVANT = {RiskType.MATERIAL_SHORTAGE, RiskType.INVENTORY_BELOW_SAFETY_STOCK}


def generate(ctx: RecommendationContext, builder: RecommendationBuilder) -> None:
    """Propose expediting POs or replenishing from an alternate supplier."""
    for risk in ctx.risk_report.risks:
        if risk.risk_type not in _RELEVANT:
            continue
        for product_id in risk.affected_entities.get("product_ids", []):
            inbound = ctx.inbound_pos_by_product.get(product_id, [])
            priority = priority_from_severity(risk.severity)

            if inbound:
                po_ids = [po.po_id for po in inbound]
                builder.add(
                    action=RecommendationAction.EXPEDITE_PURCHASE_ORDER,
                    addresses_risk_ids=[risk.risk_id],
                    title=f"Expedite inbound purchase orders for {product_id}",
                    description=(
                        f"Expedite inbound purchase order(s) {', '.join(po_ids)} for "
                        f"{product_id} to close the supply gap sooner."
                    ),
                    target_entities={
                        "product_ids": [product_id],
                        "purchase_order_ids": po_ids,
                    },
                    expected_impact={
                        "expedite_pos": po_ids,
                        "earliest_arrival": inbound[0].expected_arrival.isoformat(),
                    },
                    feasibility=RecommendationFeasibility.REQUIRES_APPROVAL,
                    priority=priority,
                )
            else:
                current = ctx.suppliers_by_product.get(product_id, set())
                alternates = sorted(ctx.all_supplier_ids - current)
                feasibility = (
                    RecommendationFeasibility.FEASIBLE
                    if alternates
                    else RecommendationFeasibility.INFEASIBLE
                )
                builder.add(
                    action=RecommendationAction.REPLENISH_ALTERNATE_SUPPLIER,
                    addresses_risk_ids=[risk.risk_id],
                    title=f"Replenish {product_id} from an alternate supplier",
                    description=(
                        f"No inbound purchase order covers {product_id}. Raise a "
                        "replenishment order"
                        + (
                            f" with an alternate supplier: {', '.join(alternates[:3])}."
                            if alternates
                            else "; no alternate supplier is on file."
                        )
                    ),
                    target_entities={
                        "product_ids": [product_id],
                        "alternate_supplier_ids": alternates[:3],
                    },
                    expected_impact={"alternate_suppliers": alternates[:3]},
                    feasibility=feasibility,
                    priority=priority,
                )
