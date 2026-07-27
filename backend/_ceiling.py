"""True OTD ceiling: orders that can physically be on time, incl. material timing."""

import logging
import math
from datetime import timedelta

logging.disable(logging.CRITICAL)

from app.config import get_settings
from app.domain.enums import PurchaseOrderStatus
from app.ingestion import CsvDataSource, FactoryStateLoader

s = get_settings()
loader = FactoryStateLoader(CsvDataSource(s.datasets_dir))
_INBOUND = {
    PurchaseOrderStatus.OPEN,
    PurchaseOrderStatus.CONFIRMED,
    PurchaseOrderStatus.IN_TRANSIT,
    PurchaseOrderStatus.DELAYED,
}


def material_ready_day(state, order):
    inv = {i.product_id: i for i in state.inventory}
    inbound = {}
    for po in state.purchase_orders:
        if po.status in _INBOUND:
            inbound.setdefault(po.product_id, []).append(po)
    for v in inbound.values():
        v.sort(key=lambda p: p.expected_arrival)
    ready = order.release_date
    for line in state.boms:
        if line.parent_product_id != order.product_id:
            continue
        required = math.ceil(order.quantity * line.quantity_per * (1 + line.scrap_factor))
        item = inv.get(line.component_product_id)
        avail = (item.on_hand - item.allocated) if item else 0.0
        if avail >= required:
            continue
        running = avail
        for po in inbound.get(line.component_product_id, []):
            running += po.quantity
            if running >= required:
                arr = po.expected_arrival
                arr_d = arr.date() if hasattr(arr, "date") else arr
                ready = max(ready, arr_d)
                break
    return ready


for BIZ in ["2026-07-24", "2026-07-20"]:
    state = loader.load(BIZ)
    rbp = {r.product_id: r for r in state.routings}
    late_chain = late_material = ok = total = 0
    for order in state.production_orders:
        if order.status.value not in ("RELEASED", "PLANNED", "IN_PROGRESS"):
            continue
        routing = rbp.get(order.product_id)
        if not routing:
            continue
        total += 1
        chain_min = sum(
            op.setup_minutes + math.ceil(op.run_minutes_per_unit * order.quantity)
            for op in routing.operations
        )
        start_day = material_ready_day(state, order)
        earliest_finish = start_day + timedelta(minutes=chain_min)
        if earliest_finish > order.due_date:
            if start_day > order.release_date:
                late_material += 1
            else:
                late_chain += 1
        else:
            ok += 1
    print(
        f"{BIZ}: on-time-possible={ok}/{total} ({ok/total:.0%}) | "
        f"blocked by MATERIALS={late_material}, by chain length={late_chain}",
        flush=True,
    )
