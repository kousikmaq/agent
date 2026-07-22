"""Event: purchase order arrivals (goods receipt).

Purchase orders whose expected arrival has reached the business date are
received: their status becomes RECEIVED and the ordered quantity is credited to
inventory on-hand.
"""

from __future__ import annotations

from app.domain.enums import ChangeEventType, PurchaseOrderStatus
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Receive any purchase orders due on or before the business date."""
    inventory_by_product = {item.product_id: item for item in state.inventory}

    for po in state.purchase_orders:
        if po.status == PurchaseOrderStatus.RECEIVED:
            continue
        if po.status == PurchaseOrderStatus.CANCELLED:
            continue
        if po.expected_arrival > ctx.business_date:
            continue

        item = inventory_by_product.get(po.product_id)
        before_on_hand = item.on_hand if item else None
        previous_status = po.status

        po.status = PurchaseOrderStatus.RECEIVED
        if item is not None:
            item.on_hand += po.quantity

        ctx.log.record(
            event_type=ChangeEventType.PURCHASE_ORDER_ARRIVAL,
            entity_type="purchase_order",
            entity_id=po.po_id,
            description=(
                f"PO {po.po_id} received: {po.quantity} of {po.product_id} added "
                "to inventory."
            ),
            before={"status": str(previous_status), "on_hand": before_on_hand},
            after={
                "status": str(po.status),
                "on_hand": item.on_hand if item else None,
            },
        )
