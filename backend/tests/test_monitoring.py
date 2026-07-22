"""Tests for delivery drift and shop-floor status views."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.analytics import (
    build_delivery_drift,
    build_delivery_report,
    build_shopfloor_status,
)
from app.analytics.deliveries import DeliveryStatus, DriftTrend
from app.domain.enums import (
    MachineStatus,
    OrderStatus,
    RiskSeverity,
    RiskType,
    SolverStatus,
    WorkerAvailabilityStatus,
)
from app.domain.models.factory_state import FactoryState
from app.domain.models.inventory import InventoryItem
from app.domain.models.machine import Machine
from app.domain.models.production_order import ProductionOrder
from app.domain.models.risk import Risk, RiskReport
from app.domain.models.schedule import ScheduledOperation, ScheduleResult
from app.domain.models.workforce import Worker, WorkerAvailability

BIZ = date(2026, 7, 20)


def _order(order_id: str, due: date) -> ProductionOrder:
    return ProductionOrder(
        order_id=order_id, product_id="FG-1", quantity=10,
        release_date=BIZ, due_date=due, status=OrderStatus.RELEASED,
    )


def _schedule(business_date: str, order_id: str, end: datetime) -> ScheduleResult:
    return ScheduleResult(
        business_date=business_date,
        status=SolverStatus.OPTIMAL,
        scheduled_operations=[
            ScheduledOperation(
                order_id=order_id, operation_id="OP-1", machine_id="M-1",
                worker_id=None, start=end - timedelta(hours=1), end=end,
            )
        ],
        makespan_minutes=60,
    )


def _state(business_date: str, order: ProductionOrder) -> FactoryState:
    return FactoryState(
        business_date=business_date,
        production_orders=[order],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )


def test_delivery_report_flags_late_and_on_track() -> None:
    state = _state("2026-07-20", _order("ORD-1", due=BIZ + timedelta(days=2)))
    # Completes well before due -> on track.
    report = build_delivery_report(
        state, _schedule("2026-07-20", "ORD-1", datetime(2026, 7, 21, 10, 0))
    )
    assert report.total == 1
    assert report.lines[0].status is DeliveryStatus.ON_TRACK


def test_delivery_drift_detects_slipping() -> None:
    order = _order("ORD-1", due=BIZ + timedelta(days=3))
    prev = build_delivery_report(
        _state("2026-07-19", order),
        _schedule("2026-07-19", "ORD-1", datetime(2026, 7, 21, 8, 0)),
    )
    curr = build_delivery_report(
        _state("2026-07-20", order),
        _schedule("2026-07-20", "ORD-1", datetime(2026, 7, 22, 8, 0)),  # +1 day
    )
    drift = build_delivery_drift(curr, prev)
    assert drift.slipping == 1
    assert drift.lines[0].trend is DriftTrend.SLIPPING
    assert drift.lines[0].delta_minutes == 1440


def test_delivery_drift_new_order_has_no_previous() -> None:
    order = _order("ORD-9", due=BIZ + timedelta(days=3))
    curr = build_delivery_report(
        _state("2026-07-20", order),
        _schedule("2026-07-20", "ORD-9", datetime(2026, 7, 22, 8, 0)),
    )
    drift = build_delivery_drift(curr, previous=None)
    assert drift.new == 1
    assert drift.lines[0].trend is DriftTrend.NEW


def test_shopfloor_status_summarises_state() -> None:
    state = FactoryState(
        business_date="2026-07-20",
        production_orders=[
            _order("ORD-1", BIZ + timedelta(days=2)),
            ProductionOrder(
                order_id="ORD-2", product_id="FG-1", quantity=5,
                release_date=BIZ, due_date=BIZ + timedelta(days=1),
                status=OrderStatus.IN_PROGRESS,
            ),
        ],
        machines=[
            Machine(machine_id="M-1", name="A", work_center="WC"),
            Machine(machine_id="M-2", name="B", work_center="WC", status=MachineStatus.DOWN),
        ],
        workers=[Worker(worker_id="W-1", name="Alice"), Worker(worker_id="W-2", name="Bob")],
        worker_availability=[
            WorkerAvailability(
                worker_id="W-2", day=BIZ,
                status=WorkerAvailabilityStatus.ON_LEAVE,
            )
        ],
        inventory=[
            InventoryItem(product_id="RM-1", on_hand=5, safety_stock=100, reorder_point=200),
        ],
    )
    risks = RiskReport(
        business_date="2026-07-20",
        risks=[
            Risk(risk_id="R1", risk_type=RiskType.MACHINE_OVERLOAD,
                 severity=RiskSeverity.CRITICAL, title="t", description="d"),
        ],
    )
    status = build_shopfloor_status(state, risks)

    assert status.machine_total == 2
    assert status.machine_down == 1
    assert len(status.machines_attention) == 1
    assert status.worker_available == 1
    assert status.worker_unavailable == 1
    assert status.orders_in_progress == 1
    assert status.materials_below_safety == 1
    assert status.critical_risks == 1


# --- Weekly plan + daily progress ---


def _week_state(business_date: str, *orders: ProductionOrder) -> FactoryState:
    return FactoryState(
        business_date=business_date,
        production_orders=list(orders),
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )


def _op(order_id: str, op_id: str, end: datetime) -> ScheduledOperation:
    return ScheduledOperation(
        order_id=order_id, operation_id=op_id, machine_id="M-1",
        worker_id=None, start=end - timedelta(hours=2), end=end,
    )


def test_weekly_plan_buckets_operations_into_days() -> None:
    from app.analytics import build_weekly_plan
    from app.analytics.weekly import WeeklyDayStatus

    order = _order("ORD-1", due=BIZ + timedelta(days=6))
    schedule = ScheduleResult(
        business_date="2026-07-20",
        status=SolverStatus.OPTIMAL,
        scheduled_operations=[
            _op("ORD-1", "OP-1", datetime(2026, 7, 20, 10, 0)),  # day 0
            _op("ORD-1", "OP-2", datetime(2026, 7, 22, 10, 0)),  # day 2 (completes)
        ],
        makespan_minutes=120,
    )
    report = build_weekly_plan(_week_state("2026-07-20", order), schedule)

    assert report.week_start == "2026-07-20"
    assert report.week_end == "2026-07-25"  # Monday..Saturday
    assert len(report.days) == 6
    assert report.planned_operations == 2
    # Weekly cadence: set the Saturday before, refreshed on this week's Saturday.
    assert report.plan_set_on == "2026-07-18"
    assert report.next_update_on == "2026-07-25"
    assert report.update_due is False
    # Order completes on day 2 -> 1 order, 10 units planned that day.
    day2 = next(d for d in report.days if d.date == "2026-07-22")
    assert day2.planned_orders == 1
    assert day2.planned_units == 10
    # Default as_of = week_start -> only day 0 is past.
    day0 = report.days[0]
    assert day0.is_past is True
    assert day0.actual_operations is not None
    assert day2.is_past is False
    assert day2.actual_operations is None
    assert day2.status is WeeklyDayStatus.PLANNED


def test_weekly_plan_progress_to_date_uses_as_of() -> None:
    from app.analytics import build_weekly_plan

    order = _order("ORD-1", due=BIZ + timedelta(days=6))
    schedule = ScheduleResult(
        business_date="2026-07-20",
        status=SolverStatus.OPTIMAL,
        scheduled_operations=[
            _op("ORD-1", "OP-1", datetime(2026, 7, 20, 10, 0)),
            _op("ORD-1", "OP-2", datetime(2026, 7, 21, 10, 0)),
            _op("ORD-1", "OP-3", datetime(2026, 7, 24, 10, 0)),
        ],
        makespan_minutes=180,
    )
    report = build_weekly_plan(
        _week_state("2026-07-20", order), schedule, as_of="2026-07-21"
    )

    # Days 0 and 1 are elapsed (2 ops planned to date); day 3's op is future.
    assert report.planned_to_date_operations == 2
    assert report.actual_to_date_operations > 0
    assert report.attainment_to_date is not None
    future = next(d for d in report.days if d.date == "2026-07-24")
    assert future.is_past is False

