"""Scenario transforms.

Each transform takes a *clone* of the factory state and applies a what-if
change using levers the CP-SAT model actually responds to (machine earliest
availability, usable machines, machine parallelism). Transforms never mutate the
original snapshot - the engine always passes a deep copy.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from app.domain.enums import MachineStatus, MaintenanceType
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import Machine, MachineAvailability
from app.utils.datetime_utils import parse_business_date

_DEFAULT_START = time(6, 0)
_DEFAULT_END = time(22, 0)


def _operating_window(state: FactoryState, business_date) -> tuple[time, time]:
    """Infer the plant's daily operating window from existing availability."""
    starts = [
        w.available_from.time()
        for w in state.machine_availability
        if w.day == business_date
    ]
    ends = [
        w.available_to.time()
        for w in state.machine_availability
        if w.day == business_date
    ]
    start = min(starts) if starts else _DEFAULT_START
    end = max(ends) if ends else _DEFAULT_END
    return start, end


def apply_current_plan(state: FactoryState, params: dict[str, Any]) -> FactoryState:
    """Baseline: return the state unchanged."""
    return state


def apply_overtime(state: FactoryState, params: dict[str, Any]) -> FactoryState:
    """Overtime enabled: extend labour coverage so machines run longer.

    Three solver-visible levers realise the extra working hours:

    * machine availability is brought forward to the start of day, so
      operations can begin earlier (the earliest-start lever);
    * every worker is flagged as overtime-eligible (used by the cost model and
      recommendations); and
    * planned *preventive* maintenance is deferred out of the horizon, because
      the extra staffing keeps machines running through what would otherwise be
      planned downtime. This frees genuine machine capacity that the scheduler
      can use, which is what distinguishes overtime from the baseline. (Breakdown
      maintenance is left untouched -- returning down machines to service is the
      Alternate Machines scenario, not this one.)
    """
    for window in state.machine_availability:
        window.available_from = datetime.combine(window.day, time(0, 0))
    for worker in state.workers:
        worker.overtime_allowed = True
    state.machine_maintenance = [
        m
        for m in state.machine_maintenance
        if m.maintenance_type != MaintenanceType.PREVENTIVE
    ]
    return state


def apply_alternate_machines(state: FactoryState, params: dict[str, Any]) -> FactoryState:
    """Alternate machines: widen the usable machine pool with backups.

    Returns any down machines to service, clears unplanned breakdown
    maintenance (assumed repaired), and brings **one backup machine per work
    centre** online as an alternate. Each backup mirrors a representative
    machine in its centre and is added to the eligibility of that centre's
    operations, so the scheduler has genuinely more places to run work. This is
    a milder capacity lever than Additional Shift (which duplicates every
    machine), keeping the two scenarios distinct.
    """
    business_date = parse_business_date(state.business_date)
    start_time, end_time = _operating_window(state, business_date)

    for machine in state.machines:
        if machine.status == MachineStatus.DOWN:
            machine.status = MachineStatus.AVAILABLE

    # Remove unplanned breakdown maintenance (assumed repaired in this scenario).
    state.machine_maintenance = [
        m for m in state.machine_maintenance if m.maintenance_type != MaintenanceType.BREAKDOWN
    ]

    # Bring one backup machine per work centre online as an alternate.
    representatives: dict[str, Machine] = {}
    for machine in state.machines:
        if machine.status != MachineStatus.DOWN:
            representatives.setdefault(machine.work_center, machine)
    backup_of_wc: dict[str, str] = {}
    for work_center, rep in representatives.items():
        backup_id = f"{rep.machine_id}-BK"
        backup_of_wc[work_center] = backup_id
        state.machines.append(
            Machine(
                machine_id=backup_id,
                name=f"{rep.name} (Backup)",
                work_center=work_center,
                status=MachineStatus.AVAILABLE,
                capacity_minutes_per_day=rep.capacity_minutes_per_day,
                efficiency_factor=rep.efficiency_factor,
            )
        )
        state.machine_availability.append(
            MachineAvailability(
                machine_id=backup_id,
                day=business_date,
                available_from=datetime.combine(business_date, start_time),
                available_to=datetime.combine(business_date, end_time),
            )
        )

    # Extend each operation's eligibility to its work centre's backup machine.
    wc_of = {m.machine_id: m.work_center for m in state.machines}
    for routing in state.routings:
        for operation in routing.operations:
            work_centers = {
                wc_of.get(mid) for mid in operation.eligible_machine_ids
            }
            extra = [
                backup_of_wc[wc] for wc in work_centers if wc in backup_of_wc
            ]
            if extra:
                operation.eligible_machine_ids = [
                    *operation.eligible_machine_ids,
                    *extra,
                ]

    machines_with_windows = {w.machine_id for w in state.machine_availability}
    for machine in state.machines:
        if machine.machine_id not in machines_with_windows:
            state.machine_availability.append(
                MachineAvailability(
                    machine_id=machine.machine_id,
                    day=business_date,
                    available_from=datetime.combine(business_date, start_time),
                    available_to=datetime.combine(business_date, end_time),
                )
            )
    return state


def apply_additional_shift(state: FactoryState, params: dict[str, Any]) -> FactoryState:
    """Additional shift: add a parallel night-shift machine per existing machine.

    Doubling machine capacity (and extending operation eligibility to the new
    machines) increases parallelism, shortening the critical path. Each night
    machine inherits its source machine's availability windows so it is usable
    exactly when the source is.
    """
    suffix = params.get("suffix", "-N")

    windows_by_machine: dict[str, list[MachineAvailability]] = {}
    for window in state.machine_availability:
        windows_by_machine.setdefault(window.machine_id, []).append(window)

    original_machines = list(state.machines)
    duplicate_of: dict[str, str] = {}
    for machine in original_machines:
        if machine.status == MachineStatus.DOWN:
            continue
        night_id = f"{machine.machine_id}{suffix}"
        duplicate_of[machine.machine_id] = night_id
        state.machines.append(
            Machine(
                machine_id=night_id,
                name=f"{machine.name} (Night)",
                work_center=machine.work_center,
                status=MachineStatus.AVAILABLE,
                capacity_minutes_per_day=machine.capacity_minutes_per_day,
                efficiency_factor=machine.efficiency_factor,
            )
        )
        # Mirror the source machine's availability windows (same hours).
        for window in windows_by_machine.get(machine.machine_id, []):
            state.machine_availability.append(
                MachineAvailability(
                    machine_id=night_id,
                    day=window.day,
                    available_from=window.available_from,
                    available_to=window.available_to,
                )
            )

    # Extend operation eligibility to include the new night-shift machines.
    for routing in state.routings:
        for operation in routing.operations:
            extra = [
                duplicate_of[m]
                for m in operation.eligible_machine_ids
                if m in duplicate_of
            ]
            if extra:
                operation.eligible_machine_ids = [
                    *operation.eligible_machine_ids,
                    *extra,
                ]
    return state
