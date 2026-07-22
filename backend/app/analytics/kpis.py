"""KPI computation.

Deterministically derives key performance indicators from a generated schedule
and the factory snapshot it was built from. Shared aggregation (per-order
outcomes and per-machine usage) is computed once and reused by both the KPI
summary and the structured facts (:mod:`app.analytics.facts`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app.domain.enums import OrderStatus
from app.analytics.cost import estimate_costs
from app.domain.models.analytics import KpiSet
from app.domain.models.factory_state import FactoryState
from app.domain.models.schedule import ScheduledOperation, ScheduleResult
from app.utils.datetime_utils import parse_business_date

_MINUTES_PER_DAY = 1440


@dataclass
class OrderOutcome:
    """Computed scheduling outcome for a single production order."""

    order_id: str
    product_id: str
    priority: int
    due_date: date
    completion: datetime | None
    tardiness_minutes: int
    on_time: bool


@dataclass
class MachineUsage:
    """Computed utilisation for a single machine."""

    machine_id: str
    busy_minutes: int
    available_minutes: int
    utilization: float  # clamped to [0, 1]


@dataclass
class ScheduleAggregates:
    """Reusable aggregation of a schedule, computed once."""

    business_date: str
    order_outcomes: list[OrderOutcome] = field(default_factory=list)
    machine_usage: list[MachineUsage] = field(default_factory=list)
    scheduled_order_ids: set[str] = field(default_factory=set)
    makespan_minutes: int = 0
    total_processing_minutes: int = 0
    total_operations: int = 0
    work_in_progress: int = 0


def _minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def aggregate_schedule(
    state: FactoryState, schedule: ScheduleResult
) -> ScheduleAggregates:
    """Compute the shared per-order and per-machine aggregates for a schedule."""
    business_date = parse_business_date(state.business_date)
    base = datetime.combine(business_date, time(0, 0))

    ops_by_order: dict[str, list[ScheduledOperation]] = {}
    ops_by_machine: dict[str, list[ScheduledOperation]] = {}
    for op in schedule.scheduled_operations:
        ops_by_order.setdefault(op.order_id, []).append(op)
        ops_by_machine.setdefault(op.machine_id, []).append(op)

    order_by_id = {o.order_id: o for o in state.production_orders}

    aggregates = ScheduleAggregates(business_date=state.business_date)
    aggregates.scheduled_order_ids = set(ops_by_order)
    aggregates.total_operations = len(schedule.scheduled_operations)

    # --- Per-order outcomes ---
    for order_id, ops in ops_by_order.items():
        order = order_by_id.get(order_id)
        if order is None:
            continue
        completion = max(op.end for op in ops)
        due_dt = datetime.combine(order.due_date, time(0, 0)) + timedelta(
            minutes=_MINUTES_PER_DAY
        )
        tardiness = max(0, _minutes_between(due_dt, completion))
        aggregates.order_outcomes.append(
            OrderOutcome(
                order_id=order_id,
                product_id=order.product_id,
                priority=order.priority,
                due_date=order.due_date,
                completion=completion,
                tardiness_minutes=tardiness,
                on_time=tardiness == 0,
            )
        )
        aggregates.makespan_minutes = max(
            aggregates.makespan_minutes, _minutes_between(base, completion)
        )

    # --- Per-machine usage ---
    available_by_machine = _available_minutes_by_machine(state, business_date)
    machine_ids = set(available_by_machine) | set(ops_by_machine)
    for machine_id in sorted(machine_ids):
        busy = sum(_minutes_between(op.start, op.end) for op in ops_by_machine.get(machine_id, []))
        available = available_by_machine.get(machine_id, 0)
        if available > 0:
            utilization = min(1.0, busy / available)
        else:
            utilization = 1.0 if busy > 0 else 0.0
        aggregates.machine_usage.append(
            MachineUsage(
                machine_id=machine_id,
                busy_minutes=busy,
                available_minutes=available,
                utilization=round(utilization, 4),
            )
        )
        aggregates.total_processing_minutes += busy

    # --- Work in progress (orders currently in progress) ---
    aggregates.work_in_progress = sum(
        1 for o in state.production_orders if o.status == OrderStatus.IN_PROGRESS
    )

    return aggregates


def _available_minutes_by_machine(
    state: FactoryState, business_date: date
) -> dict[str, int]:
    """Total available minutes per machine on the business date."""
    available: dict[str, int] = {}
    for window in state.machine_availability:
        if window.day != business_date:
            continue
        minutes = _minutes_between(window.available_from, window.available_to)
        available[window.machine_id] = available.get(window.machine_id, 0) + max(0, minutes)
    # Machines with no availability window fall back to their daily capacity.
    for machine in state.machines:
        available.setdefault(machine.machine_id, machine.capacity_minutes_per_day)
    return available


class AnalyticsEngine:
    """Computes KPI summaries from schedules."""

    def compute(self, state: FactoryState, schedule: ScheduleResult) -> KpiSet:
        """Return the :class:`KpiSet` for a schedule."""
        aggregates = aggregate_schedule(state, schedule)
        kpis = self._to_kpis(aggregates, schedule)
        costs = estimate_costs(
            state,
            schedule,
            total_busy_machine_minutes=aggregates.total_processing_minutes,
            total_tardiness_minutes=sum(
                o.tardiness_minutes for o in aggregates.order_outcomes
            ),
        )
        return kpis.model_copy(update={"metrics": {**kpis.metrics, **costs}})

    @staticmethod
    def _to_kpis(aggregates: ScheduleAggregates, schedule: ScheduleResult) -> KpiSet:
        scheduled_orders = len(aggregates.scheduled_order_ids)
        on_time_orders = sum(1 for o in aggregates.order_outcomes if o.on_time)
        late_orders = scheduled_orders - on_time_orders
        total_tardiness = sum(o.tardiness_minutes for o in aggregates.order_outcomes)
        tardiness_values = [o.tardiness_minutes for o in aggregates.order_outcomes]

        machine_utils = [m.utilization for m in aggregates.machine_usage]
        avg_utilization = (
            round(sum(machine_utils) / len(machine_utils), 4) if machine_utils else 0.0
        )

        otd = (on_time_orders / scheduled_orders) if scheduled_orders else None

        makespan = (
            schedule.makespan_minutes
            if schedule.makespan_minutes is not None
            else aggregates.makespan_minutes
        )

        metrics = {
            "scheduled_orders": float(scheduled_orders),
            "on_time_orders": float(on_time_orders),
            "late_orders": float(late_orders),
            "max_tardiness_minutes": float(max(tardiness_values) if tardiness_values else 0),
            "average_tardiness_minutes": round(
                sum(tardiness_values) / len(tardiness_values), 2
            )
            if tardiness_values
            else 0.0,
            "makespan_minutes": float(makespan or 0),
            "total_scheduled_operations": float(aggregates.total_operations),
            "total_processing_minutes": float(aggregates.total_processing_minutes),
            "machines_utilized": float(
                sum(1 for m in aggregates.machine_usage if m.busy_minutes > 0)
            ),
            "total_available_machine_minutes": float(
                sum(m.available_minutes for m in aggregates.machine_usage)
            ),
            "total_busy_machine_minutes": float(
                sum(m.busy_minutes for m in aggregates.machine_usage)
            ),
        }

        return KpiSet(
            business_date=aggregates.business_date,
            on_time_delivery_rate=round(otd, 4) if otd is not None else None,
            average_machine_utilization=avg_utilization,
            total_tardiness_minutes=int(total_tardiness),
            work_in_progress=aggregates.work_in_progress,
            metrics=metrics,
        )
