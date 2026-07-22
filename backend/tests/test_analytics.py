"""Phase 7 tests: the analytics / KPI engine.

Uses hand-built schedules for exact KPI arithmetic plus a small solver
integration check.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.analytics import AnalyticsEngine, build_analytics_facts
from app.domain.enums import OrderStatus, SolverStatus
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import Machine, MachineAvailability
from app.domain.models.production_order import ProductionOrder
from app.domain.models.schedule import ScheduledOperation, ScheduleResult

BIZ = date(2026, 7, 17)


def _order(order_id: str, due: date, status: OrderStatus = OrderStatus.RELEASED) -> ProductionOrder:
    return ProductionOrder(
        order_id=order_id,
        product_id="FG-1",
        quantity=10,
        release_date=BIZ,
        due_date=due,
        priority=5,
        status=status,
    )


def _op(order_id: str, machine_id: str, start: datetime, end: datetime) -> ScheduledOperation:
    return ScheduledOperation(
        order_id=order_id,
        operation_id=f"OP-{order_id}",
        machine_id=machine_id,
        worker_id=None,
        start=start,
        end=end,
    )


def _schedule(*ops: ScheduledOperation) -> ScheduleResult:
    makespan = 0
    base = datetime.combine(BIZ, time(0, 0))
    for op in ops:
        makespan = max(makespan, int((op.end - base).total_seconds() // 60))
    return ScheduleResult(
        business_date="2026-07-17",
        status=SolverStatus.OPTIMAL,
        scheduled_operations=list(ops),
        makespan_minutes=makespan,
    )


def test_tardiness_and_otd_for_late_order() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ)],  # due end = 2026-07-18 00:00
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    # Completes 2 hours past the due-date end -> 120 minutes late.
    schedule = _schedule(
        _op(
            "ORD-1",
            "M-1",
            datetime(2026, 7, 18, 0, 0),
            datetime(2026, 7, 18, 2, 0),
        )
    )
    kpis = AnalyticsEngine().compute(state, schedule)
    assert kpis.total_tardiness_minutes == 120
    assert kpis.on_time_delivery_rate == 0.0
    assert kpis.metrics["late_orders"] == 1.0


def test_on_time_order_scores_full_otd() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + timedelta(days=5))],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    schedule = _schedule(
        _op("ORD-1", "M-1", datetime(2026, 7, 17, 6, 0), datetime(2026, 7, 17, 8, 0))
    )
    kpis = AnalyticsEngine().compute(state, schedule)
    assert kpis.on_time_delivery_rate == 1.0
    assert kpis.total_tardiness_minutes == 0


def test_machine_utilization_from_availability() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + timedelta(days=5))],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
        machine_availability=[
            MachineAvailability(
                machine_id="M-1",
                day=BIZ,
                available_from=datetime(2026, 7, 17, 6, 0),
                available_to=datetime(2026, 7, 17, 14, 0),  # 480 minutes
            )
        ],
    )
    # 120 busy minutes out of 480 available -> 0.25 utilisation.
    schedule = _schedule(
        _op("ORD-1", "M-1", datetime(2026, 7, 17, 6, 0), datetime(2026, 7, 17, 8, 0))
    )
    kpis = AnalyticsEngine().compute(state, schedule)
    assert kpis.average_machine_utilization == 0.25


def test_work_in_progress_counts_in_progress_orders() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[
            _order("ORD-1", due=BIZ + timedelta(days=5), status=OrderStatus.IN_PROGRESS),
            _order("ORD-2", due=BIZ + timedelta(days=5)),
        ],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    schedule = _schedule(
        _op("ORD-1", "M-1", datetime(2026, 7, 17, 6, 0), datetime(2026, 7, 17, 8, 0))
    )
    kpis = AnalyticsEngine().compute(state, schedule)
    assert kpis.work_in_progress == 1


def test_empty_schedule_yields_null_otd() -> None:
    state = FactoryState(business_date="2026-07-17")
    schedule = _schedule()
    kpis = AnalyticsEngine().compute(state, schedule)
    assert kpis.on_time_delivery_rate is None
    assert kpis.average_machine_utilization == 0.0
    assert kpis.total_tardiness_minutes == 0


def test_facts_report_late_orders() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ)],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    schedule = _schedule(
        _op("ORD-1", "M-1", datetime(2026, 7, 18, 0, 0), datetime(2026, 7, 18, 3, 0))
    )
    kpis = AnalyticsEngine().compute(state, schedule)
    facts = build_analytics_facts(state, schedule, kpis)
    assert facts.late_orders == 1
    assert facts.late_order_details[0].order_id == "ORD-1"
    assert facts.late_order_details[0].tardiness_minutes == 180


def test_integration_with_solver() -> None:
    from datetime import timedelta as _td

    from app.domain.models.product import Product
    from app.domain.models.routing import Operation, Routing
    from app.optimization import SchedulingSolver, SolverOptions
    from app.rules import BusinessRulesEngine

    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + _td(days=5))],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[
            Routing(
                routing_id="RT-1",
                product_id="FG-1",
                operations=[
                    Operation(
                        operation_id="OP-1",
                        routing_id="RT-1",
                        sequence=1,
                        name="Cut",
                        work_center="WC",
                        run_minutes_per_unit=1.0,
                        eligible_machine_ids=["M-1"],
                    )
                ],
            )
        ],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    policy = BusinessRulesEngine().evaluate(state)
    schedule = SchedulingSolver(SolverOptions(max_time_seconds=5)).solve(state, policy)
    kpis = AnalyticsEngine().compute(state, schedule)
    assert kpis.on_time_delivery_rate == 1.0
    assert kpis.metrics["total_scheduled_operations"] == 1.0
