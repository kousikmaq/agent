"""Event: overtime approvals.

Available workers whose profile permits overtime may have overtime minutes
approved for the day, increasing effective labour capacity.
"""

from __future__ import annotations

from app.domain.enums import ChangeEventType, WorkerAvailabilityStatus
from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Approve overtime for a random subset of eligible workers."""
    config = ctx.config
    overtime_allowed = {
        worker.worker_id: worker.overtime_allowed for worker in state.workers
    }
    max_overtime = {
        worker.worker_id: worker.max_overtime_minutes_per_day
        for worker in state.workers
    }

    for availability in state.worker_availability:
        if availability.day != ctx.business_date:
            continue
        if availability.status != WorkerAvailabilityStatus.AVAILABLE:
            continue
        if not overtime_allowed.get(availability.worker_id, False):
            continue
        if ctx.rng.random() >= config.overtime_approval_probability:
            continue

        minutes = min(
            config.overtime_minutes,
            max_overtime.get(availability.worker_id, config.overtime_minutes),
        )
        if minutes <= 0 or availability.approved_overtime_minutes == minutes:
            continue

        previous = availability.approved_overtime_minutes
        availability.approved_overtime_minutes = minutes

        ctx.log.record(
            event_type=ChangeEventType.OVERTIME_APPROVAL,
            entity_type="worker",
            entity_id=availability.worker_id,
            description=(
                f"Approved {minutes} overtime minutes for "
                f"{availability.worker_id}."
            ),
            before={"approved_overtime_minutes": previous},
            after={"approved_overtime_minutes": minutes},
        )
