"""Event: capacity changes.

Machine daily capacity may fluctuate (efficiency drives, tooling changes,
partial staffing), nudging ``capacity_minutes_per_day`` up or down within a
configured band for available machines.
"""

from __future__ import annotations

from app.domain.enums import ChangeEventType, MachineStatus
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext

_MIN_CAPACITY_MINUTES = 240  # never drop below a half-shift


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Adjust the daily capacity of a random subset of available machines."""
    config = ctx.config
    for machine in state.machines:
        if machine.status == MachineStatus.DOWN:
            continue
        if ctx.rng.random() >= config.capacity_change_probability:
            continue

        delta_fraction = ctx.rng.uniform(
            -config.capacity_change_fraction, config.capacity_change_fraction
        )
        previous = machine.capacity_minutes_per_day
        new_capacity = int(round(previous * (1 + delta_fraction)))
        new_capacity = max(_MIN_CAPACITY_MINUTES, new_capacity)
        if new_capacity == previous:
            continue

        machine.capacity_minutes_per_day = new_capacity

        ctx.log.record(
            event_type=ChangeEventType.CAPACITY_CHANGE,
            entity_type="machine",
            entity_id=machine.machine_id,
            description=(
                f"Machine {machine.machine_id} capacity changed "
                f"{previous} -> {new_capacity} min/day."
            ),
            before={"capacity_minutes_per_day": previous},
            after={"capacity_minutes_per_day": new_capacity},
        )
