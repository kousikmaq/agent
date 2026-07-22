"""Delivery commitments view.

Turns a generated schedule into a delivery-commitments board: for each order due
within a horizon (e.g. the next week), it reports the scheduled completion and a
red/amber/green status against the order's due date. Purely a view over the
existing analytics aggregation - no scheduling logic and no new business rules.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from enum import Enum

from pydantic import Field

from app.analytics.kpis import aggregate_schedule
from app.domain.enums import OrderStatus
from app.domain.models.base import FrozenDomainModel
from app.domain.models.factory_state import FactoryState
from app.domain.models.schedule import ScheduleResult
from app.utils.datetime_utils import parse_business_date

_SCHEDULABLE = {OrderStatus.PLANNED, OrderStatus.RELEASED, OrderStatus.IN_PROGRESS}
_MINUTES_PER_DAY = 1440
# Default slack below which an on-time order is flagged "at risk" (tight).
_DEFAULT_AT_RISK_MINUTES = 8 * 60


class DeliveryStatus(str, Enum):
    """Red/amber/green delivery status against a due date."""

    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    LATE = "LATE"
    UNSCHEDULED = "UNSCHEDULED"


class DeliveryLine(FrozenDomainModel):
    """Delivery commitment status for a single order."""

    order_id: str
    product_id: str
    customer_id: str | None
    customer_tier: str | None
    due_date: str
    scheduled_completion: str | None
    tardiness_minutes: int
    slack_minutes: int | None
    priority: int
    status: DeliveryStatus


class DeliveryReport(FrozenDomainModel):
    """Delivery commitments for orders due within the horizon."""

    business_date: str
    horizon_days: int
    total: int
    on_track: int
    at_risk: int
    late: int
    unscheduled: int
    on_time_rate: float | None
    lines: list[DeliveryLine] = Field(default_factory=list)


# Ordering for sorting lines by urgency of status.
_STATUS_RANK = {
    DeliveryStatus.LATE: 0,
    DeliveryStatus.UNSCHEDULED: 1,
    DeliveryStatus.AT_RISK: 2,
    DeliveryStatus.ON_TRACK: 3,
}


def build_delivery_report(
    state: FactoryState,
    schedule: ScheduleResult,
    horizon_days: int = 7,
    at_risk_minutes: int = _DEFAULT_AT_RISK_MINUTES,
) -> DeliveryReport:
    """Build the delivery commitments report for a scheduled day."""
    business_date = parse_business_date(state.business_date)
    horizon_end = business_date + timedelta(days=horizon_days)

    aggregates = aggregate_schedule(state, schedule)
    outcome_by_id = {o.order_id: o for o in aggregates.order_outcomes}
    tier_by_customer = {c.customer_id: str(c.tier) for c in state.customers}

    lines: list[DeliveryLine] = []
    for order in state.production_orders:
        if order.status not in _SCHEDULABLE:
            continue
        outcome = outcome_by_id.get(order.order_id)
        is_late = outcome is not None and outcome.tardiness_minutes > 0
        # Only orders due within the horizon (plus any already late) are commitments.
        if order.due_date > horizon_end and not is_late:
            continue

        completion = outcome.completion if outcome else None
        tardiness = outcome.tardiness_minutes if outcome else 0
        slack = _slack_minutes(order.due_date, completion)
        status = _status(completion, tardiness, slack, at_risk_minutes)

        lines.append(
            DeliveryLine(
                order_id=order.order_id,
                product_id=order.product_id,
                customer_id=order.customer_id,
                customer_tier=tier_by_customer.get(order.customer_id or ""),
                due_date=order.due_date.isoformat(),
                scheduled_completion=completion.isoformat() if completion else None,
                tardiness_minutes=tardiness,
                slack_minutes=slack,
                priority=order.priority,
                status=status,
            )
        )

    lines.sort(key=lambda ln: (_STATUS_RANK[ln.status], ln.due_date, ln.order_id))

    on_track = sum(1 for ln in lines if ln.status is DeliveryStatus.ON_TRACK)
    at_risk = sum(1 for ln in lines if ln.status is DeliveryStatus.AT_RISK)
    late = sum(1 for ln in lines if ln.status is DeliveryStatus.LATE)
    unscheduled = sum(1 for ln in lines if ln.status is DeliveryStatus.UNSCHEDULED)
    total = len(lines)
    on_time_rate = (on_track / total) if total else None

    return DeliveryReport(
        business_date=state.business_date,
        horizon_days=horizon_days,
        total=total,
        on_track=on_track,
        at_risk=at_risk,
        late=late,
        unscheduled=unscheduled,
        on_time_rate=round(on_time_rate, 4) if on_time_rate is not None else None,
        lines=lines,
    )


def _due_datetime(due: date) -> datetime:
    """End of the due date (deliveries are on time if completed by day end)."""
    return datetime.combine(due, time(0, 0)) + timedelta(minutes=_MINUTES_PER_DAY)


def _slack_minutes(due: date, completion: datetime | None) -> int | None:
    if completion is None:
        return None
    return int((_due_datetime(due) - completion).total_seconds() // 60)


def _status(
    completion: datetime | None,
    tardiness: int,
    slack: int | None,
    at_risk_minutes: int,
) -> DeliveryStatus:
    if completion is None:
        return DeliveryStatus.UNSCHEDULED
    if tardiness > 0:
        return DeliveryStatus.LATE
    if slack is not None and slack < at_risk_minutes:
        return DeliveryStatus.AT_RISK
    return DeliveryStatus.ON_TRACK


# ---------------------------------------------------------------------------
# Commitment drift: plan-vs-prior-plan comparison (variance over time)
# ---------------------------------------------------------------------------
# Minutes of change below which a commitment is considered stable.
_DEFAULT_DRIFT_THRESHOLD_MINUTES = 60


class DriftTrend(str, Enum):
    """How an order's scheduled completion moved versus the prior plan."""

    IMPROVING = "IMPROVING"  # pulled earlier
    STABLE = "STABLE"
    SLIPPING = "SLIPPING"  # pushed later
    NEW = "NEW"  # not present in the prior plan


class DriftLine(FrozenDomainModel):
    """Commitment drift for a single order between two consecutive plans."""

    order_id: str
    due_date: str
    current_completion: str | None
    previous_completion: str | None
    delta_minutes: int | None  # positive = slipping later, negative = earlier
    current_status: DeliveryStatus
    previous_status: DeliveryStatus | None
    trend: DriftTrend


class DeliveryDriftReport(FrozenDomainModel):
    """Day-over-day movement of delivery commitments (plan vs prior plan)."""

    business_date: str
    previous_date: str | None
    total: int
    slipping: int
    improving: int
    stable: int
    new: int
    lines: list[DriftLine] = Field(default_factory=list)


_TREND_RANK = {
    DriftTrend.SLIPPING: 0,
    DriftTrend.NEW: 1,
    DriftTrend.STABLE: 2,
    DriftTrend.IMPROVING: 3,
}


def build_delivery_drift(
    current: DeliveryReport,
    previous: DeliveryReport | None,
    threshold_minutes: int = _DEFAULT_DRIFT_THRESHOLD_MINUTES,
) -> DeliveryDriftReport:
    """Compare the current delivery plan against the previous one per order."""
    prev_by_id = (
        {ln.order_id: ln for ln in previous.lines} if previous is not None else {}
    )

    lines: list[DriftLine] = []
    for line in current.lines:
        prev = prev_by_id.get(line.order_id)
        delta = _completion_delta(line.scheduled_completion, prev)
        trend = _drift_trend(prev, delta, threshold_minutes)
        lines.append(
            DriftLine(
                order_id=line.order_id,
                due_date=line.due_date,
                current_completion=line.scheduled_completion,
                previous_completion=prev.scheduled_completion if prev else None,
                delta_minutes=delta,
                current_status=line.status,
                previous_status=prev.status if prev else None,
                trend=trend,
            )
        )

    lines.sort(key=lambda ln: (_TREND_RANK[ln.trend], ln.due_date, ln.order_id))

    return DeliveryDriftReport(
        business_date=current.business_date,
        previous_date=previous.business_date if previous else None,
        total=len(lines),
        slipping=sum(1 for ln in lines if ln.trend is DriftTrend.SLIPPING),
        improving=sum(1 for ln in lines if ln.trend is DriftTrend.IMPROVING),
        stable=sum(1 for ln in lines if ln.trend is DriftTrend.STABLE),
        new=sum(1 for ln in lines if ln.trend is DriftTrend.NEW),
        lines=lines,
    )


def _completion_delta(
    current_completion: str | None, prev: DeliveryLine | None
) -> int | None:
    if prev is None or current_completion is None or prev.scheduled_completion is None:
        return None
    cur = datetime.fromisoformat(current_completion)
    old = datetime.fromisoformat(prev.scheduled_completion)
    return int((cur - old).total_seconds() // 60)


def _drift_trend(
    prev: DeliveryLine | None, delta: int | None, threshold: int
) -> DriftTrend:
    if prev is None:
        return DriftTrend.NEW
    if delta is None or abs(delta) <= threshold:
        return DriftTrend.STABLE
    return DriftTrend.SLIPPING if delta > 0 else DriftTrend.IMPROVING
