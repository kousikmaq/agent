"""Detector: capacity shortage.

Compares the total processing time demanded of each work center (from
schedulable orders' routings) against the available machine capacity of that
work center on the business date. A shortfall means the work center cannot
absorb its demand within a single day of capacity.
"""

from __future__ import annotations

from app.domain.enums import OrderStatus, RiskSeverity, RiskType
from app.risk.result import RiskBuilder, RiskContext, operation_duration

_SCHEDULABLE = {OrderStatus.PLANNED, OrderStatus.RELEASED, OrderStatus.IN_PROGRESS}


def _severity(ratio: float) -> RiskSeverity:
    if ratio >= 2.0:
        return RiskSeverity.CRITICAL
    if ratio >= 1.5:
        return RiskSeverity.HIGH
    return RiskSeverity.MEDIUM


def detect(ctx: RiskContext, builder: RiskBuilder) -> None:
    """Emit a CAPACITY_SHORTAGE risk per over-demanded work center."""
    state = ctx.state
    routing_by_product = {r.product_id: r for r in state.routings}

    # Demanded minutes and contributing orders per work center.
    demand: dict[str, int] = {}
    orders_by_wc: dict[str, set[str]] = {}
    for order in state.production_orders:
        if order.status not in _SCHEDULABLE:
            continue
        routing = routing_by_product.get(order.product_id)
        if routing is None:
            continue
        for operation in routing.operations:
            duration = operation_duration(operation, order.quantity)
            demand[operation.work_center] = demand.get(operation.work_center, 0) + duration
            orders_by_wc.setdefault(operation.work_center, set()).add(order.order_id)

    # Available minutes per work center (sum of member machines).
    available: dict[str, int] = {}
    for machine in state.machines:
        usage = ctx.machine_usage_by_id.get(machine.machine_id)
        minutes = usage.available_minutes if usage else machine.capacity_minutes_per_day
        available[machine.work_center] = available.get(machine.work_center, 0) + minutes

    for work_center, demanded in demand.items():
        capacity = available.get(work_center, 0)
        if capacity <= 0 or demanded <= capacity:
            continue
        ratio = demanded / capacity
        builder.add(
            risk_type=RiskType.CAPACITY_SHORTAGE,
            severity=_severity(ratio),
            title=f"Capacity shortage in {work_center} ({ratio:.0%} of capacity)",
            description=(
                f"Work center {work_center} demands {demanded} minute(s) against "
                f"{capacity} available minute(s) of machine capacity."
            ),
            affected_entities={
                "work_centers": [work_center],
                "order_ids": sorted(orders_by_wc.get(work_center, set())),
            },
            evidence={
                "demanded_minutes": demanded,
                "available_minutes": capacity,
                "shortfall_minutes": demanded - capacity,
                "demand_ratio": round(ratio, 4),
            },
        )
