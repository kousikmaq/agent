"""Weekly plan and daily progress view.

Turns a generated schedule into a *weekly plan*: the total workload for a
7-day window, broken down into per-day targets ("this much work should be done
each day"). Given an as-of date ("today"), it compares the actual progress of
elapsed days against those targets to answer "are we on track?".

This is a view over the existing schedule aggregation - no scheduling logic and
no new business rules. Until a real-time execution feed is wired in, actuals for
elapsed days are produced by :func:`_simulate_day_actual`, which is deliberately
isolated so it can be swapped for real completion data without touching the
report shape.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum

from pydantic import Field

from app.domain.models.base import FrozenDomainModel
from app.domain.models.factory_state import FactoryState
from app.domain.models.schedule import ScheduleResult
from app.utils.datetime_utils import parse_business_date

_WORKING_DAYS = 6  # Monday..Saturday (Sunday is not a working day)
# Cumulative attainment thresholds for the on-track banner.
_ON_TRACK_MIN = 0.95
_AT_RISK_MIN = 0.85
_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class WeeklyDayStatus(str, Enum):
    """On-track status of a single day (or the week overall)."""

    PLANNED = "PLANNED"  # future day - target only, no actuals yet
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    BEHIND = "BEHIND"


class WeeklyDayPlan(FrozenDomainModel):
    """Planned target and (for elapsed days) actual progress for one day."""

    date: str
    weekday: str
    is_past: bool
    is_today: bool
    planned_operations: int
    planned_minutes: int
    planned_orders: int
    planned_units: int
    actual_operations: int | None
    actual_minutes: int | None
    actual_orders: int | None
    actual_units: int | None
    attainment: float | None  # actual_operations / planned_operations
    status: WeeklyDayStatus


class WeeklyPlanReport(FrozenDomainModel):
    """A 7-day plan with per-day targets and progress-to-date."""

    business_date: str  # the schedule the plan is derived from
    as_of_date: str  # "today" for progress purposes
    week_start: str
    week_end: str
    # Weekly cadence: the plan is refreshed every Saturday for the next week.
    plan_set_on: str  # the Saturday the current week's plan was drawn up
    next_update_on: str  # the Saturday the plan is next refreshed
    update_due: bool  # the weekly update is due (today is on/after that Saturday)
    # Week totals (all 7 days).
    planned_operations: int
    planned_minutes: int
    planned_orders: int
    planned_units: int
    # Progress to date (elapsed days only).
    planned_to_date_operations: int
    planned_to_date_units: int
    actual_to_date_operations: int
    actual_to_date_units: int
    attainment_to_date: float | None
    overall_status: WeeklyDayStatus
    days: list[WeeklyDayPlan] = Field(default_factory=list)


def _simulate_day_actual(day: date, planned: int) -> int:
    """Deterministically derive an elapsed day's actual output from its target.

    Placeholder for a real execution feed: produces a stable per-day attainment
    factor in [0.80, 1.05] so the on-track view is demonstrable. Swap this for
    real completion data when the live feed is available.
    """
    if planned <= 0:
        return 0
    factor = 0.80 + ((day.toordinal() * 7) % 26) / 100.0  # 0.80 .. 1.05
    return round(planned * factor)


def _status_for(attainment: float | None) -> WeeklyDayStatus:
    if attainment is None:
        return WeeklyDayStatus.PLANNED
    if attainment >= _ON_TRACK_MIN:
        return WeeklyDayStatus.ON_TRACK
    if attainment >= _AT_RISK_MIN:
        return WeeklyDayStatus.AT_RISK
    return WeeklyDayStatus.BEHIND


def build_weekly_plan(
    state: FactoryState,
    schedule: ScheduleResult,
    as_of: str | None = None,
) -> WeeklyPlanReport:
    """Build the weekly plan + daily-progress report for a scheduled week.

    The week is the Monday-Saturday working week containing the schedule's
    business date. Days on or before ``as_of`` are treated as elapsed (progress
    known); later days are future targets. ``as_of`` defaults to the schedule's
    business date.
    """
    anchor = parse_business_date(state.business_date)
    week_start = anchor - timedelta(days=anchor.weekday())  # Monday of the week
    week_end = week_start + timedelta(days=_WORKING_DAYS - 1)  # Saturday
    as_of_date = parse_business_date(as_of) if as_of else anchor
    # Clamp as-of into the week window.
    as_of_date = min(max(as_of_date, week_start), week_end)

    quantity_by_order = {o.order_id: o.quantity for o in state.production_orders}

    # Per-day planned work: operations bucketed by their completion day.
    planned_ops: dict[date, int] = {}
    planned_minutes: dict[date, int] = {}
    order_completion: dict[str, date] = {}
    for op in schedule.scheduled_operations:
        end_day = op.end.date()
        if not (week_start <= end_day <= week_end):
            continue
        planned_ops[end_day] = planned_ops.get(end_day, 0) + 1
        minutes = int((op.end - op.start).total_seconds() // 60)
        planned_minutes[end_day] = planned_minutes.get(end_day, 0) + minutes
        # Track the latest op end per order = the day the order completes.
        prev = order_completion.get(op.order_id)
        if prev is None or end_day > prev:
            order_completion[op.order_id] = end_day

    planned_orders: dict[date, int] = {}
    planned_units: dict[date, int] = {}
    for order_id, comp_day in order_completion.items():
        planned_orders[comp_day] = planned_orders.get(comp_day, 0) + 1
        planned_units[comp_day] = planned_units.get(comp_day, 0) + quantity_by_order.get(
            order_id, 0
        )

    days: list[WeeklyDayPlan] = []
    ptd_ops = ptd_units = atd_ops = atd_units = 0
    for offset in range(_WORKING_DAYS):
        day = week_start + timedelta(days=offset)
        p_ops = planned_ops.get(day, 0)
        p_min = planned_minutes.get(day, 0)
        p_ord = planned_orders.get(day, 0)
        p_units = planned_units.get(day, 0)
        is_past = day <= as_of_date

        if is_past:
            factor_ops = _simulate_day_actual(day, p_ops)
            a_ops: int | None = factor_ops
            a_min: int | None = _simulate_day_actual(day, p_min)
            a_ord: int | None = _simulate_day_actual(day, p_ord)
            a_units: int | None = _simulate_day_actual(day, p_units)
            attainment = round(a_ops / p_ops, 4) if p_ops > 0 else None
            status = _status_for(attainment if p_ops > 0 else 1.0)
            ptd_ops += p_ops
            ptd_units += p_units
            atd_ops += a_ops
            atd_units += a_units
        else:
            a_ops = a_min = a_ord = a_units = None
            attainment = None
            status = WeeklyDayStatus.PLANNED

        days.append(
            WeeklyDayPlan(
                date=day.isoformat(),
                weekday=_WEEKDAY_NAMES[day.weekday()],
                is_past=is_past,
                is_today=day == as_of_date,
                planned_operations=p_ops,
                planned_minutes=p_min,
                planned_orders=p_ord,
                planned_units=p_units,
                actual_operations=a_ops,
                actual_minutes=a_min,
                actual_orders=a_ord,
                actual_units=a_units,
                attainment=attainment,
                status=status,
            )
        )

    attainment_to_date = round(atd_ops / ptd_ops, 4) if ptd_ops > 0 else None
    overall_status = _status_for(attainment_to_date)

    # Weekly cadence: plan is set the Saturday before the week and refreshed on
    # the week's own Saturday (week_end) for the following week.
    plan_set_on = week_start - timedelta(days=2)  # Saturday before Monday
    next_update_on = week_end  # Saturday of this week

    return WeeklyPlanReport(
        business_date=state.business_date,
        as_of_date=as_of_date.isoformat(),
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        plan_set_on=plan_set_on.isoformat(),
        next_update_on=next_update_on.isoformat(),
        update_due=as_of_date >= next_update_on,
        planned_operations=sum(planned_ops.values()),
        planned_minutes=sum(planned_minutes.values()),
        planned_orders=sum(planned_orders.values()),
        planned_units=sum(planned_units.values()),
        planned_to_date_operations=ptd_ops,
        planned_to_date_units=ptd_units,
        actual_to_date_operations=atd_ops,
        actual_to_date_units=atd_units,
        attainment_to_date=attainment_to_date,
        overall_status=overall_status,
        days=days,
    )
