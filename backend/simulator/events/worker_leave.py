"""Event: worker leave.

Some workers are marked unavailable for the day (annual leave or sickness),
updating their availability record for the business date.
"""

from __future__ import annotations

from app.domain.enums import ChangeEventType, WorkerAvailabilityStatus
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Place a random subset of workers on leave / sick for the day."""
    config = ctx.config
    for availability in state.worker_availability:
        if availability.day != ctx.business_date:
            continue
        if availability.status != WorkerAvailabilityStatus.AVAILABLE:
            continue
        if ctx.rng.random() >= config.worker_leave_probability:
            continue

        new_status = ctx.rng.choice(
            [WorkerAvailabilityStatus.ON_LEAVE, WorkerAvailabilityStatus.SICK]
        )
        previous_status = availability.status
        # Clear any overtime before changing status (invariant on the model).
        availability.approved_overtime_minutes = 0
        availability.status = new_status

        ctx.log.record(
            event_type=ChangeEventType.WORKER_LEAVE,
            entity_type="worker",
            entity_id=availability.worker_id,
            description=(
                f"Worker {availability.worker_id} unavailable ({new_status}) on "
                f"{ctx.business_date_str}."
            ),
            before={"status": str(previous_status)},
            after={"status": str(new_status)},
        )
