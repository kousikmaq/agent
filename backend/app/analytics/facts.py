"""Structured analytics facts.

Curated, serialisable summaries of a schedule's performance derived from the
same aggregation the KPIs use. These facts are the analytics contribution to
the Explanation Context Builder (later phase) - concise, grounded, and safe to
present to the LLM. This module computes no new scheduling logic.
"""

from __future__ import annotations

from app.analytics.kpis import aggregate_schedule
from app.domain.models.analytics import KpiSet
from app.domain.models.base import FrozenDomainModel
from app.domain.models.factory_state import FactoryState
from app.domain.models.schedule import ScheduleResult


class LateOrderFact(FrozenDomainModel):
    """Details of one order that misses its due date."""

    order_id: str
    product_id: str
    priority: int
    due_date: str
    completion: str | None
    tardiness_minutes: int


class MachineUtilizationFact(FrozenDomainModel):
    """Utilisation detail for one machine."""

    machine_id: str
    busy_minutes: int
    available_minutes: int
    utilization: float


class AnalyticsFacts(FrozenDomainModel):
    """Curated performance facts for a scheduled production day."""

    business_date: str
    scheduled_orders: int
    on_time_orders: int
    late_orders: int
    on_time_delivery_rate: float | None
    average_machine_utilization: float
    total_tardiness_minutes: int
    makespan_minutes: int
    late_order_details: list[LateOrderFact]
    machine_utilization: list[MachineUtilizationFact]


def build_analytics_facts(
    state: FactoryState, schedule: ScheduleResult, kpis: KpiSet
) -> AnalyticsFacts:
    """Assemble structured performance facts from a schedule and its KPIs."""
    aggregates = aggregate_schedule(state, schedule)

    late_details = [
        LateOrderFact(
            order_id=o.order_id,
            product_id=o.product_id,
            priority=o.priority,
            due_date=o.due_date.isoformat(),
            completion=o.completion.isoformat() if o.completion else None,
            tardiness_minutes=o.tardiness_minutes,
        )
        for o in sorted(
            aggregates.order_outcomes,
            key=lambda outcome: outcome.tardiness_minutes,
            reverse=True,
        )
        if not o.on_time
    ]

    machine_utilization = [
        MachineUtilizationFact(
            machine_id=m.machine_id,
            busy_minutes=m.busy_minutes,
            available_minutes=m.available_minutes,
            utilization=m.utilization,
        )
        for m in aggregates.machine_usage
    ]

    on_time = sum(1 for o in aggregates.order_outcomes if o.on_time)
    scheduled = len(aggregates.scheduled_order_ids)

    return AnalyticsFacts(
        business_date=state.business_date,
        scheduled_orders=scheduled,
        on_time_orders=on_time,
        late_orders=scheduled - on_time,
        on_time_delivery_rate=kpis.on_time_delivery_rate,
        average_machine_utilization=kpis.average_machine_utilization or 0.0,
        total_tardiness_minutes=kpis.total_tardiness_minutes or 0,
        makespan_minutes=int(kpis.metrics.get("makespan_minutes", 0)),
        late_order_details=late_details,
        machine_utilization=machine_utilization,
    )
