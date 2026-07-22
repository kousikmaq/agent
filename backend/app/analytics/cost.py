"""Deterministic cost estimation for a schedule.

The factory snapshot carries no labor or machine rate master data, so plan cost
is estimated from transparent, fixed default rates applied to the schedule's
labor minutes (regular + overtime), machine running time, and order lateness.
The result is directional — intended for comparing plans against each other, not
for financial accounting.
"""

from __future__ import annotations

from app.domain.models.factory_state import FactoryState
from app.domain.models.schedule import ScheduleResult

# Default rates in USD. These are explicit assumptions, surfaced to the UI so
# the estimate stays transparent and auditable.
LABOR_REGULAR_PER_MIN = 0.60  # ~$36 / hour
LABOR_OVERTIME_PER_MIN = 0.90  # 1.5x the regular rate
MACHINE_PER_MIN = 0.40  # ~$24 / hour machine running cost
TARDINESS_PENALTY_PER_MIN = 0.25  # late-delivery penalty per minute late


def estimate_costs(
    state: FactoryState,
    schedule: ScheduleResult,
    *,
    total_busy_machine_minutes: int,
    total_tardiness_minutes: int,
) -> dict[str, float]:
    """Estimate the cost breakdown of a schedule from fixed default rates."""
    workers = {w.worker_id: w for w in state.workers}

    minutes_by_worker: dict[str, int] = {}
    for op in schedule.scheduled_operations:
        if op.worker_id is None:
            continue
        minutes = int((op.end - op.start).total_seconds() // 60)
        minutes_by_worker[op.worker_id] = (
            minutes_by_worker.get(op.worker_id, 0) + minutes
        )

    regular_minutes = 0
    overtime_minutes = 0
    for worker_id, minutes in minutes_by_worker.items():
        worker = workers.get(worker_id)
        cap = worker.max_regular_minutes_per_day if worker is not None else 480
        regular_minutes += min(minutes, cap)
        overtime_minutes += max(0, minutes - cap)

    labor_regular_cost = regular_minutes * LABOR_REGULAR_PER_MIN
    labor_overtime_cost = overtime_minutes * LABOR_OVERTIME_PER_MIN
    machine_cost = total_busy_machine_minutes * MACHINE_PER_MIN
    tardiness_cost = total_tardiness_minutes * TARDINESS_PENALTY_PER_MIN
    total = labor_regular_cost + labor_overtime_cost + machine_cost + tardiness_cost

    return {
        "cost_labor_regular": round(labor_regular_cost, 2),
        "cost_labor_overtime": round(labor_overtime_cost, 2),
        "cost_machine": round(machine_cost, 2),
        "cost_tardiness_penalty": round(tardiness_cost, 2),
        "cost_total": round(total, 2),
        "cost_overtime_minutes": float(overtime_minutes),
    }
