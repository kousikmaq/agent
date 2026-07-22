"""Event: supplier delays.

In-transit / open purchase orders may be delayed by an unreliable supplier,
pushing out their expected arrival date and flagging them as DELAYED.
"""

from __future__ import annotations

from datetime import timedelta

from app.domain.enums import ChangeEventType, PurchaseOrderStatus
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext

_DELAYABLE = {
    PurchaseOrderStatus.OPEN,
    PurchaseOrderStatus.CONFIRMED,
    PurchaseOrderStatus.IN_TRANSIT,
}


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Randomly delay a subset of outstanding purchase orders."""
    config = ctx.config
    for po in state.purchase_orders:
        if po.status not in _DELAYABLE:
            continue
        if ctx.rng.random() >= config.supplier_delay_probability:
            continue

        delay_days = ctx.rng.randint(
            config.supplier_delay_days_min, config.supplier_delay_days_max
        )
        if delay_days == 0:
            continue

        before_arrival = po.expected_arrival
        previous_status = po.status
        po.expected_arrival = po.expected_arrival + timedelta(days=delay_days)
        po.status = PurchaseOrderStatus.DELAYED

        ctx.log.record(
            event_type=ChangeEventType.SUPPLIER_DELAY,
            entity_type="purchase_order",
            entity_id=po.po_id,
            description=(
                f"Supplier {po.supplier_id} delayed PO {po.po_id} by "
                f"{delay_days} day(s)."
            ),
            before={
                "status": str(previous_status),
                "expected_arrival": before_arrival.isoformat(),
            },
            after={
                "status": str(po.status),
                "expected_arrival": po.expected_arrival.isoformat(),
            },
        )
