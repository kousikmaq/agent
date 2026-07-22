"""Event: inventory consumption.

Simulates daily material usage by production: a random subset of purchased
materials is drawn down by a configured fraction, never falling below the
quantity already allocated to orders.
"""

from __future__ import annotations

from app.domain.enums import ChangeEventType
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Consume a fraction of on-hand stock for a subset of materials."""
    config = ctx.config
    purchased_ids = {p.product_id for p in state.products if p.is_purchased}

    for item in state.inventory:
        if item.product_id not in purchased_ids:
            continue
        if item.on_hand <= item.allocated:
            continue
        # Only some materials are consumed on any given day.
        if ctx.rng.random() >= 0.5:
            continue

        fraction = ctx.rng.uniform(
            config.inventory_consumption_fraction_min,
            config.inventory_consumption_fraction_max,
        )
        consumable = item.on_hand - item.allocated
        consumed = round(consumable * fraction, 2)
        if consumed <= 0:
            continue

        before_on_hand = item.on_hand
        item.on_hand = round(item.on_hand - consumed, 2)

        ctx.log.record(
            event_type=ChangeEventType.INVENTORY_CONSUMPTION,
            entity_type="inventory",
            entity_id=item.product_id,
            description=(
                f"Consumed {consumed} of {item.product_id} "
                f"({before_on_hand} -> {item.on_hand})."
            ),
            before={"on_hand": before_on_hand},
            after={"on_hand": item.on_hand},
        )
