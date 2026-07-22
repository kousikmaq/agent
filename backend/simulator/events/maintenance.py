"""Event: planned maintenance scheduling.

Available machines may have preventive maintenance planned for an upcoming day
within the maintenance horizon, adding a future maintenance window without
affecting the current day's availability.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from app.domain.enums import ChangeEventType, MachineStatus, MaintenanceType
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import MachineMaintenance
from simulator.change_log import SimulationContext
from simulator.utils import IdSequencer


def apply(state: FactoryState, ctx: SimulationContext) -> None:
    """Schedule preventive maintenance windows for a subset of machines."""
    config = ctx.config
    maintenance_ids = IdSequencer(
        "MT-", [m.maintenance_id for m in state.machine_maintenance]
    )

    for machine in state.machines:
        if machine.status != MachineStatus.AVAILABLE:
            continue
        if ctx.rng.random() >= config.planned_maintenance_probability:
            continue

        offset = ctx.rng.randint(1, config.planned_maintenance_horizon_days)
        maintenance_day = ctx.business_date + timedelta(days=offset)
        start_hour = ctx.rng.randint(6, 16)
        duration_hours = ctx.rng.randint(2, 6)
        start = datetime.combine(maintenance_day, time(start_hour, 0))
        end = start + timedelta(hours=duration_hours)

        maintenance = MachineMaintenance(
            maintenance_id=maintenance_ids.next(),
            machine_id=machine.machine_id,
            maintenance_type=MaintenanceType.PREVENTIVE,
            start=start,
            end=end,
            description="Scheduled preventive maintenance.",
        )
        state.machine_maintenance.append(maintenance)

        ctx.log.record(
            event_type=ChangeEventType.PLANNED_MAINTENANCE,
            entity_type="machine",
            entity_id=machine.machine_id,
            description=(
                f"Preventive maintenance {maintenance.maintenance_id} planned for "
                f"{machine.machine_id} on {maintenance_day.isoformat()}."
            ),
            after={
                "maintenance_id": maintenance.maintenance_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
