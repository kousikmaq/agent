"""Event: order cancellations.

A small fraction of active production orders are cancelled each day (customer
changes, demand drops), transitioning them to the CANCELLED status while
preserving them for historical traceability.
"""

from __future__ import annotations

from app.domain.enums import ChangeEventType, OrderStatus
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext

_ACTIVE = {
    OrderStatus.PLANNED,
    OrderStatus.RELEASED,
    OrderStatus.IN_PROGRESS,
    OrderStatus.ON_HOLD,
}


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Cancel a random subset of active production orders."""
    config = ctx.config
    for order in state.production_orders:
        if order.status not in _ACTIVE:
            continue
        if ctx.rng.random() >= config.order_cancel_probability:
            continue

        previous_status = order.status
        order.status = OrderStatus.CANCELLED

        ctx.log.record(
            event_type=ChangeEventType.ORDER_CANCELLATION,
            entity_type="production_order",
            entity_id=order.order_id,
            description=f"Order {order.order_id} cancelled.",
            before={"status": str(previous_status)},
            after={"status": str(order.status)},
        )
