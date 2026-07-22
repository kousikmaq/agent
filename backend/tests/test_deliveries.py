"""Tests for the delivery commitments view."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.analytics import DeliveryStatus, build_delivery_report
from app.domain.enums import CustomerTier, OrderStatus, SolverStatus
from app.domain.models.customer import Customer
from app.domain.models.factory_state import FactoryState
from app.domain.models.production_order import ProductionOrder
from app.domain.models.schedule import ScheduledOperation, ScheduleResult

BIZ = date(2026, 7, 17)


def _order(order_id: str, due: date, customer: str | None = None) -> ProductionOrder:
    return ProductionOrder(
        order_id=order_id, product_id="FG-1", customer_id=customer, quantity=10,
        release_date=BIZ, due_date=due, status=OrderStatus.RELEASED,
    )


def _op(order_id: str, end: datetime) -> ScheduledOperation:
    return ScheduledOperation(
        order_id=order_id, operation_id=f"OP-{order_id}", machine_id="M-1",
        worker_id=None, start=datetime(2026, 7, 17, 6, 0), end=end,
    )


def _schedule(*ops: ScheduledOperation) -> ScheduleResult:
    return ScheduleResult(
        business_date="2026-07-17", status=SolverStatus.OPTIMAL,
        scheduled_operations=list(ops),
    )


def test_delivery_statuses_are_classified() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        customers=[Customer(customer_id="CU-1", name="A", tier=CustomerTier.STRATEGIC)],
        production_orders=[
            _order("ON", due=BIZ + timedelta(days=5), customer="CU-1"),
            _order("LATE", due=BIZ),
            _order("TIGHT", due=BIZ + timedelta(days=1)),
            _order("NOSCHED", due=BIZ + timedelta(days=3)),
        ],
    )
    schedule = _schedule(
        # ON: finishes well before its due-date end -> ON_TRACK
        _op("ON", datetime(2026, 7, 20, 8, 0)),
        # LATE: finishes after due-date end (2026-07-18 00:00) -> LATE
        _op("LATE", datetime(2026, 7, 18, 3, 0)),
        # TIGHT: finishes shortly before due end (2026-07-19 00:00) -> AT_RISK
        _op("TIGHT", datetime(2026, 7, 18, 22, 0)),
        # NOSCHED has no operation -> UNSCHEDULED
    )

    report = build_delivery_report(state, schedule, horizon_days=7)
    by_id = {ln.order_id: ln for ln in report.lines}

    assert by_id["ON"].status is DeliveryStatus.ON_TRACK
    assert by_id["ON"].customer_tier == "STRATEGIC"
    assert by_id["LATE"].status is DeliveryStatus.LATE
    assert by_id["LATE"].tardiness_minutes > 0
    assert by_id["TIGHT"].status is DeliveryStatus.AT_RISK
    assert by_id["NOSCHED"].status is DeliveryStatus.UNSCHEDULED
    assert report.total == 4
    assert report.late == 1 and report.on_track == 1


def test_horizon_excludes_far_future_orders() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[
            _order("SOON", due=BIZ + timedelta(days=3)),
            _order("FAR", due=BIZ + timedelta(days=30)),
        ],
    )
    schedule = _schedule(
        _op("SOON", datetime(2026, 7, 18, 8, 0)),
        _op("FAR", datetime(2026, 7, 18, 8, 0)),
    )
    report = build_delivery_report(state, schedule, horizon_days=7)
    ids = {ln.order_id for ln in report.lines}
    assert "SOON" in ids and "FAR" not in ids
