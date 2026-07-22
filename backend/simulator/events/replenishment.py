"""Event: material replenishment.

When a purchased material's on-hand stock falls below its reorder point and no
outstanding purchase order already covers it, a new purchase order is raised
with the supplying vendor.
"""

from __future__ import annotations

from datetime import timedelta

from app.domain.enums import ChangeEventType, PurchaseOrderStatus
from app.domain.models.factory_state import FactoryState
from app.domain.models.purchase_order import PurchaseOrder
from simulator.change_log import SimulationContext
from simulator.utils import IdSequencer

_OUTSTANDING = {
    PurchaseOrderStatus.OPEN,
    PurchaseOrderStatus.CONFIRMED,
    PurchaseOrderStatus.IN_TRANSIT,
    PurchaseOrderStatus.DELAYED,
}


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Raise replenishment purchase orders for materials below reorder point."""
    if not ctx.config.replenish_when_below_reorder:
        return

    purchased_ids = {p.product_id for p in state.products if p.is_purchased}
    suppliers_by_id = {s.supplier_id: s for s in state.suppliers}

    # Materials already covered by an outstanding PO should not be re-ordered.
    covered = {
        po.product_id
        for po in state.purchase_orders
        if po.status in _OUTSTANDING
    }
    # Preferred supplier per material inferred from historical POs.
    preferred_supplier = {
        po.product_id: po.supplier_id for po in state.purchase_orders
    }

    po_ids = IdSequencer("PO-", [po.po_id for po in state.purchase_orders])

    for item in state.inventory:
        if item.product_id not in purchased_ids:
            continue
        if item.on_hand >= item.reorder_point:
            continue
        if item.product_id in covered:
            continue

        supplier_id = preferred_supplier.get(item.product_id)
        if supplier_id is None and state.suppliers:
            supplier_id = ctx.rng.choice(state.suppliers).supplier_id
        if supplier_id is None:
            continue

        lead = suppliers_by_id[supplier_id].lead_time_days if supplier_id in suppliers_by_id else 5
        order_quantity = max(item.reorder_point * 2 - item.on_hand, item.reorder_point)
        new_po = PurchaseOrder(
            po_id=po_ids.next(),
            supplier_id=supplier_id,
            product_id=item.product_id,
            quantity=round(order_quantity, 2),
            order_date=ctx.business_date,
            expected_arrival=ctx.business_date + timedelta(days=lead),
            status=PurchaseOrderStatus.CONFIRMED,
        )
        state.purchase_orders.append(new_po)
        covered.add(item.product_id)

        ctx.log.record(
            event_type=ChangeEventType.MATERIAL_REPLENISHMENT,
            entity_type="purchase_order",
            entity_id=new_po.po_id,
            description=(
                f"Raised PO {new_po.po_id} for {new_po.quantity} of "
                f"{item.product_id} (on_hand {item.on_hand} < reorder "
                f"{item.reorder_point})."
            ),
            after={
                "product_id": new_po.product_id,
                "quantity": new_po.quantity,
                "expected_arrival": new_po.expected_arrival.isoformat(),
            },
        )
