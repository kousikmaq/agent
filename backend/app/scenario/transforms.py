"""Scenario transforms.

Each transform takes a *clone* of the factory state and applies a what-if
change using levers the CP-SAT model actually responds to (machine earliest
availability, usable machines, machine parallelism, and qualified-worker
capacity). Transforms never mutate the original snapshot - the engine always
passes a deep copy.

Note on "working hours": the scheduler models time continuously (single
operations can run for >24h, so they cannot be confined to a daily shift
window). "Overtime" therefore cannot add clock hours; instead it adds parallel
labour capacity (extra qualified worker slots), which is the lever the CP-SAT
workforce constraint actually responds to under load.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from app.domain.enums import (
    MachineStatus,
    MaintenanceType,
    WorkerAvailabilityStatus,
)
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import Machine, MachineAvailability
from app.domain.models.workforce import Worker, WorkerSkill
from app.utils.datetime_utils import parse_business_date

_DEFAULT_START = time(6, 0)
_DEFAULT_END = time(22, 0)


def _available_worker_ids(state: FactoryState, business_date) -> set[str]:
    """Worker ids available on the business date (mirrors the solver's rule).

    A worker is unavailable only if they have a same-day record whose status is
    not AVAILABLE (leave/sick/training); everyone else is available.
    """
    unavailable = {
        record.worker_id
        for record in state.worker_availability
        if record.day == business_date
        and record.status != WorkerAvailabilityStatus.AVAILABLE
    }
    return {w.worker_id for w in state.workers if w.worker_id not in unavailable}


def _add_worker_crew(
    state: FactoryState, business_date, suffix: str, crew_label: str
) -> None:
    """Clone each available worker (with their skills) as an extra crew.

    Adds parallel labour capacity for every skill the current workforce holds,
    so the CP-SAT workforce no-overlap constraint has more qualified workers to
    staff concurrent operations. New workers carry no availability record, so
    the solver treats them as available.
    """
    available = _available_worker_ids(state, business_date)
    skills_by_worker: dict[str, list[WorkerSkill]] = {}
    for skill in state.worker_skills:
        skills_by_worker.setdefault(skill.worker_id, []).append(skill)

    for worker in list(state.workers):
        if worker.worker_id not in available:
            continue
        crew_id = f"{worker.worker_id}{suffix}"
        state.workers.append(
            Worker(
                worker_id=crew_id,
                name=f"{worker.name} ({crew_label})",
                home_shift_id=worker.home_shift_id,
                max_regular_minutes_per_day=worker.max_regular_minutes_per_day,
                max_overtime_minutes_per_day=worker.max_overtime_minutes_per_day,
                overtime_allowed=True,
            )
        )
        for skill in skills_by_worker.get(worker.worker_id, []):
            state.worker_skills.append(
                WorkerSkill(
                    worker_id=crew_id,
                    skill=skill.skill,
                    proficiency=skill.proficiency,
                )
            )


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
    """Overtime enabled: extend labour coverage so more work runs in parallel.

    This is the *labour* lever (no extra machines). Because the scheduler models
    time continuously, overtime cannot add clock hours; it instead adds parallel
    qualified-worker capacity -- the existing crew working an overtime shift --
    which the CP-SAT workforce constraint responds to when skilled labour is the
    bottleneck. Concretely:

    * every available worker gains an overtime twin with the same skills, so
      more same-skill operations can be staffed concurrently;
    * machine availability is brought forward to the start of day (earliest-start
      lever); every worker is flagged overtime-eligible (cost model); and
    * planned *preventive* maintenance is deferred out of the horizon, since the
      extra staffing keeps machines running through planned downtime. (Breakdown
      maintenance is left untouched -- repairing down machines is the Alternate
      Machines scenario.)
    """
    business_date = parse_business_date(state.business_date)
    _add_worker_crew(state, business_date, suffix="-OT", crew_label="Overtime")

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
    """Additional shift: add a full parallel night shift (machines **and** crew).

    A real extra shift adds both equipment and the people to run it, so this
    transform:

    * adds a parallel night-shift machine per existing machine (doubling machine
      capacity and extending operation eligibility to the new machines); and
    * adds a night crew -- an extra qualified worker per available worker -- so
      the new machines can actually be staffed.

    Adding both resources increases parallelism on whichever of machines or
    skilled labour is binding, shortening the critical path. Each night machine
    inherits its source machine's availability windows so it is usable exactly
    when the source is.
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

    # Staff the new shift: add a night crew mirroring the current workforce so
    # the extra machines can actually be run.
    business_date = parse_business_date(state.business_date)
    _add_worker_crew(state, business_date, suffix="-N", crew_label="Night")
    return state
