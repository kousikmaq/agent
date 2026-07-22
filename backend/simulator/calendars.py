"""Per-day calendar construction.

Builds the date-specific collections (machine availability, shift calendars,
worker availability) for a single production day. Shared by the Day-0 seed
generator and the daily "roll" so both produce identical calendar semantics.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.domain.enums import MachineStatus, WorkerAvailabilityStatus
from app.domain.models.machine import Machine, MachineAvailability
from app.domain.models.shift_calendar import Shift, ShiftCalendar
from app.domain.models.workforce import Worker, WorkerAvailability
from simulator.config import SimulatorConfig

# Canonical plant shift templates used across the simulator.
STANDARD_SHIFTS: tuple[Shift, ...] = (
    Shift(
        shift_id="SHIFT_MORNING",
        shift_type="MORNING",
        start_time=time(6, 0),
        end_time=time(14, 0),
        break_minutes=30,
    ),
    Shift(
        shift_id="SHIFT_AFTERNOON",
        shift_type="AFTERNOON",
        start_time=time(14, 0),
        end_time=time(22, 0),
        break_minutes=30,
    ),
    Shift(
        shift_id="SHIFT_NIGHT",
        shift_type="NIGHT",
        start_time=time(22, 0),
        end_time=time(6, 0),
        break_minutes=30,
    ),
)


def shift_window(shift: Shift, day: date) -> tuple[datetime, datetime]:
    """Return the concrete ``(start, end)`` datetimes for a shift on a day.

    Overnight shifts (end <= start) roll their end into the following day.
    """
    start = datetime.combine(day, shift.start_time)
    end_day = day + timedelta(days=1) if shift.end_time <= shift.start_time else day
    end = datetime.combine(end_day, shift.end_time)
    return start, end


def build_machine_availability(
    machines: list[Machine], day: date, config: SimulatorConfig
) -> list[MachineAvailability]:
    """Create availability windows for all non-down machines on ``day``."""
    shifts_by_id = {shift.shift_id: shift for shift in STANDARD_SHIFTS}
    windows: list[MachineAvailability] = []
    for machine in machines:
        if machine.status == MachineStatus.DOWN:
            continue
        for shift_id in config.machine_operating_shift_ids:
            shift = shifts_by_id.get(shift_id)
            if shift is None:
                continue
            start, end = shift_window(shift, day)
            windows.append(
                MachineAvailability(
                    machine_id=machine.machine_id,
                    day=day,
                    available_from=start,
                    available_to=end,
                )
            )
    return windows


def build_machine_availability_for(
    machine: Machine, day: date, config: SimulatorConfig
) -> list[MachineAvailability]:
    """Create availability windows for a single machine on ``day``."""
    return build_machine_availability([machine], day, config)


def build_shift_calendars(day: date) -> list[ShiftCalendar]:
    """Instantiate all standard shifts on ``day``."""
    calendars: list[ShiftCalendar] = []
    for shift in STANDARD_SHIFTS:
        calendars.append(
            ShiftCalendar(
                shift_id=shift.shift_id,
                day=day,
                start_time=shift.start_time,
                end_time=shift.end_time,
                break_minutes=shift.break_minutes,
                crosses_midnight=shift.end_time <= shift.start_time,
            )
        )
    return calendars


def build_worker_availability(
    workers: list[Worker], day: date
) -> list[WorkerAvailability]:
    """Create default (available) availability records for ``day``."""
    return [
        WorkerAvailability(
            worker_id=worker.worker_id,
            day=day,
            status=WorkerAvailabilityStatus.AVAILABLE,
            shift_id=worker.home_shift_id,
            approved_overtime_minutes=0,
        )
        for worker in workers
    ]
