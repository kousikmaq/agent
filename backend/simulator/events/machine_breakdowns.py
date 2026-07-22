"""Event: machine breakdowns and recoveries.

Available machines may break down (going DOWN, losing the day's availability and
gaining a corrective maintenance window). Previously broken-down machines may
recover, returning to service with their availability restored.
"""

from __future__ import annotations

from datetime import datetime, time

from app.domain.enums import ChangeEventType, MachineStatus, MaintenanceType
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import MachineMaintenance
from simulator.calendars import build_machine_availability_for
from simulator.change_log import SimulationContext
from simulator.utils import IdSequencer


def _remove_todays_availability(state: FactoryState, machine_id: str, ctx: SimulationContext) -> None:
    state.machine_availability = [
        window
        for window in state.machine_availability
        if not (window.machine_id == machine_id and window.day == ctx.business_date)
    ]


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Apply breakdowns to running machines and recoveries to down machines."""
    config = ctx.config
    maintenance_ids = IdSequencer(
        "MT-", [m.maintenance_id for m in state.machine_maintenance]
    )
    day_end = datetime.combine(ctx.business_date, time(23, 59))

    for machine in state.machines:
        if machine.status == MachineStatus.DOWN:
            # Chance to recover and return to service.
            if ctx.rng.random() < config.machine_recovery_probability:
                machine.status = MachineStatus.AVAILABLE
                state.machine_availability.extend(
                    build_machine_availability_for(machine, ctx.business_date, config)
                )
                ctx.log.record(
                    event_type=ChangeEventType.MACHINE_BREAKDOWN,
                    entity_type="machine",
                    entity_id=machine.machine_id,
                    description=f"Machine {machine.machine_id} recovered and returned to service.",
                    before={"status": str(MachineStatus.DOWN)},
                    after={"status": str(machine.status)},
                )
            continue

        if machine.status != MachineStatus.AVAILABLE:
            continue
        if ctx.rng.random() >= config.machine_breakdown_probability:
            continue

        # Break the machine down for the remainder of the day.
        breakdown_start = datetime.combine(ctx.business_date, time(ctx.rng.randint(6, 18), 0))
        machine.status = MachineStatus.DOWN
        _remove_todays_availability(state, machine.machine_id, ctx)
        maintenance = MachineMaintenance(
            maintenance_id=maintenance_ids.next(),
            machine_id=machine.machine_id,
            maintenance_type=MaintenanceType.BREAKDOWN,
            start=breakdown_start,
            end=day_end,
            description="Unplanned breakdown repair.",
        )
        state.machine_maintenance.append(maintenance)

        ctx.log.record(
            event_type=ChangeEventType.MACHINE_BREAKDOWN,
            entity_type="machine",
            entity_id=machine.machine_id,
            description=(
                f"Machine {machine.machine_id} broke down; corrective maintenance "
                f"{maintenance.maintenance_id} scheduled."
            ),
            before={"status": str(MachineStatus.AVAILABLE)},
            after={"status": str(machine.status), "maintenance_id": maintenance.maintenance_id},
        )
