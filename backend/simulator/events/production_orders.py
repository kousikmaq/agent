"""Event: new production orders.

A bursty number of new customer orders arrives each day (drawn from a Poisson
distribution around the configured mean), each for a finished good with a
realistic quantity and due date.
"""

from __future__ import annotations

from datetime import timedelta

from app.domain.enums import ChangeEventType, OrderStatus
from app.domain.models.factory_state import FactoryState
from app.domain.models.production_order import ProductionOrder
from simulator.change_log import SimulationContext
from simulator.utils import IdSequencer, poisson


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Append newly-arrived production orders for the day."""
    config = ctx.config
    finished = [p for p in state.products if not p.is_purchased]
    if not finished or not state.customers:
        return

    count = poisson(ctx.rng, config.new_orders_mean)
    if count == 0:
        return

    order_ids = IdSequencer("ORD-", [o.order_id for o in state.production_orders])

    for _ in range(count):
        product = ctx.rng.choice(finished)
        customer = ctx.rng.choice(state.customers)
        lead = ctx.rng.randint(config.order_lead_days_min, config.order_lead_days_max)
        order = ProductionOrder(
            order_id=order_ids.next(),
            product_id=product.product_id,
            customer_id=customer.customer_id,
            quantity=ctx.rng.randint(
                config.order_quantity_min, config.order_quantity_max
            ),
            release_date=ctx.business_date,
            due_date=ctx.business_date + timedelta(days=lead),
            priority=ctx.rng.randint(1, 10),
            status=OrderStatus.RELEASED,
        )
        state.production_orders.append(order)

        ctx.log.record(
            event_type=ChangeEventType.NEW_PRODUCTION_ORDER,
            entity_type="production_order",
            entity_id=order.order_id,
            description=(
                f"New order {order.order_id}: {order.quantity} x "
                f"{order.product_id} due {order.due_date.isoformat()}."
            ),
            after={
                "product_id": order.product_id,
                "quantity": order.quantity,
                "due_date": order.due_date.isoformat(),
                "priority": order.priority,
            },
        )
