"""Event: shift changes (swaps).

Available workers may be reassigned from their home shift to a different shift
for the day, reflecting real-world shift swaps.
"""

from __future__ import annotations

from app.domain.enums import ChangeEventType, WorkerAvailabilityStatus
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Swap a random subset of available workers onto a different shift."""
    config = ctx.config
    shift_ids = [shift.shift_id for shift in state.shifts]
    if len(shift_ids) < 2:
        return

    for availability in state.worker_availability:
        if availability.day != ctx.business_date:
            continue
        if availability.status != WorkerAvailabilityStatus.AVAILABLE:
            continue
        if ctx.rng.random() >= config.shift_change_probability:
            continue

        alternatives = [s for s in shift_ids if s != availability.shift_id]
        if not alternatives:
            continue
        new_shift = ctx.rng.choice(alternatives)
        previous_shift = availability.shift_id
        availability.shift_id = new_shift

        ctx.log.record(
            event_type=ChangeEventType.SHIFT_CHANGE,
            entity_type="worker",
            entity_id=availability.worker_id,
            description=(
                f"Worker {availability.worker_id} swapped from {previous_shift} to "
                f"{new_shift}."
            ),
            before={"shift_id": previous_shift},
            after={"shift_id": new_shift},
        )
