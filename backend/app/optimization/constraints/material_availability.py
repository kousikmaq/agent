"""Constraint: material availability.

An order cannot begin until the materials its bill of materials requires are on
hand. For each order we deterministically compute the earliest minute at which
every component is available - immediately if current stock covers demand,
otherwise the arrival time of the purchase orders that make up the shortfall.
The order's first operation is then constrained to start no earlier than that.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.domain.enums import PurchaseOrderStatus

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel

# Purchase orders that will still deliver stock.
_INBOUND_STATUSES = {
    PurchaseOrderStatus.OPEN,
    PurchaseOrderStatus.CONFIRMED,
    PurchaseOrderStatus.IN_TRANSIT,
    PurchaseOrderStatus.DELAYED,
}


def _material_ready_minute(model: "SchedulingModel", order) -> int:
    """Earliest minute all BOM components for ``order`` are available."""
    inventory_by_product = {item.product_id: item for item in model.state.inventory}

    # Group inbound purchase orders by product, sorted by arrival.
    inbound: dict[str, list] = {}
    for po in model.state.purchase_orders:
        if po.status in _INBOUND_STATUSES:
            inbound.setdefault(po.product_id, []).append(po)
    for pos in inbound.values():
        pos.sort(key=lambda p: p.expected_arrival)

    ready = 0
    for line in model.state.boms:
        if line.parent_product_id != order.product_id:
            continue
        required = math.ceil(order.quantity * line.quantity_per * (1 + line.scrap_factor))

        item = inventory_by_product.get(line.component_product_id)
        available = (item.on_hand - item.allocated) if item else 0.0
        if available >= required:
            continue

        # Accumulate incoming purchase orders until the shortfall is covered.
        shortfall_covered_at = None
        running = available
        for po in inbound.get(line.component_product_id, []):
            running += po.quantity
            if running >= required:
                shortfall_covered_at = max(0, model.date_to_minute(po.expected_arrival))
                break

        if shortfall_covered_at is None:
            # Known supply cannot cover demand. We flag this for the risk engine
            # but do NOT impose an infeasible start bound - the order is planned
            # under the assumption that replenishment will be expedited.
            model.warnings.append(
                f"Order {order.order_id}: insufficient known supply of component "
                f"{line.component_product_id}; material readiness not constrained."
            )
            continue
        ready = max(ready, shortfall_covered_at)
    return ready


def add_material_availability(model: "SchedulingModel") -> None:
    """Delay each order's first operation until its materials are available."""
    cp = model.model
    for order_id, order_tasks in model.tasks_by_order.items():
        first_task = min(order_tasks, key=lambda task: task.sequence_index)
        ready = _material_ready_minute(model, first_task.order)
        if ready > 0:
            cp.Add(first_task.start >= ready)
