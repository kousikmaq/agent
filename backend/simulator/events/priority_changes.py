"""Event: order priority changes.

Active production orders may have their priority revised as customer urgency
shifts, altering their weight in the downstream optimization objective.
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
    """Revise the priority of a random subset of active orders."""
    config = ctx.config
    for order in state.production_orders:
        if order.status not in _ACTIVE:
            continue
        if ctx.rng.random() >= config.priority_change_probability:
            continue

        new_priority = ctx.rng.randint(1, 10)
        if new_priority == order.priority:
            continue

        previous_priority = order.priority
        order.priority = new_priority

        ctx.log.record(
            event_type=ChangeEventType.PRIORITY_CHANGE,
            entity_type="production_order",
            entity_id=order.order_id,
            description=(
                f"Order {order.order_id} priority changed "
                f"{previous_priority} -> {new_priority}."
            ),
            before={"priority": previous_priority},
            after={"priority": new_priority},
        )
