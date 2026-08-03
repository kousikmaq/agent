"""Event: order completions.

The plant finishes a realistic number of aged production orders each day, moving
them to COMPLETED so they leave the schedulable pool. Without this the daily
snapshot would accumulate orders forever (arrivals with no departures), inflating
the backlog until makespan and tardiness look absurd.

Dispatch rule: earliest-due-date first (EDD), a standard shop-floor heuristic —
so the plant protects the most urgent commitments. Only orders that have been in
the system at least a day are eligible (an order cannot be released and finished
on the same day), which keeps the modelled build time realistic. When more
orders are ready than the plant can finish, the overflow waits and may slip past
its due date, which is exactly how real capacity pressure creates lateness.
"""

from __future__ import annotations

from app.domain.enums import ChangeEventType, OrderStatus
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext
from simulator.utils import poisson

# Orders that represent work-in-progress the plant can finish.
_ACTIVE = {OrderStatus.RELEASED, OrderStatus.IN_PROGRESS}


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Complete a realistic number of aged orders, earliest-due first."""
    config = ctx.config
    business_date = ctx.business_date

    # Eligible = active and in the system since a prior day (aged >= 1 day).
    eligible = [
        order
        for order in state.production_orders
        if order.status in _ACTIVE and order.release_date < business_date
    ]
    if not eligible:
        return

    # Earliest-due first, then higher priority, as the dispatch order.
    eligible.sort(key=lambda o: (o.due_date, -o.priority))

    count = min(poisson(ctx.rng, config.order_completion_mean), len(eligible))
    for order in eligible[:count]:
        previous_status = order.status
        order.status = OrderStatus.COMPLETED
        on_time = business_date <= order.due_date
        ctx.log.record(
            event_type=ChangeEventType.ORDER_COMPLETION,
            entity_type="production_order",
            entity_id=order.order_id,
            description=(
                f"Order {order.order_id} completed "
                f"({'on time' if on_time else 'late'}; due {order.due_date.isoformat()})."
            ),
            before={"status": str(previous_status)},
            after={"status": str(order.status)},
        )
