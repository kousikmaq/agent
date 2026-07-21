"""
What-if Scenarios - compare planning options for a week (satisfies the brief's
"support minimum 3 planning scenarios").

All scenarios reuse the same deterministic capacity maths, just with different
inputs:
  1. Baseline        - the week as it stands.
  2. Add a shift     - give the bottleneck's department one extra shift of capacity.
  3. Defer orders    - push the least-urgent orders to a later week until the
                       bottleneck is back within capacity.
"""
import math
from collections import defaultdict
from datetime import date, timedelta

from logging_config import get_logger
from data_loader import load
from services.prioritize import prioritize_week
from models import Scenario, ScenarioComparison

log = get_logger("scenarios")
ACTIVE = {"Open", "Released"}


def _loads(week_start: date, exclude: set = frozenset(), extra_shift_depts: set = frozenset()):
    """Return (resources, bottleneck_wc, bottleneck_util, overloaded_count, orders_planned)."""
    d = load()
    wcs, routings = d["work_centers"], d["routings"]
    end = week_start + timedelta(days=7)
    orders = [o for o in d["orders"]
              if week_start <= o["due_date"] < end and o["status"] in ACTIVE
              and o["order_id"] not in exclude]

    req_min: dict = defaultdict(float)
    for o in orders:
        for op in routings.get(o["item_id"], []):
            req_min[op["work_center"]] += op["setup_min"] + op["run_min_per_unit"] * o["quantity"]

    best_wc, best_util, overloaded = None, 0.0, 0
    for wc_id, wc in wcs.items():
        req = req_min.get(wc_id, 0.0) / 60.0
        avail = wc["weekly_capacity_hours"]
        if wc["department"] in extra_shift_depts:
            avail += wc["hours_per_shift"] * wc["days_per_week"]   # one extra shift
        util = round(req / avail * 100, 1) if avail else 0.0
        if util > 100:
            overloaded += 1
        if util > best_util:
            best_util, best_wc = util, wc_id
    return best_wc, best_util, overloaded, len(orders)


def scenarios(week_start: date) -> ScenarioComparison:
    d = load()
    wcs = d["work_centers"]
    log.info("SCENARIOS  week %s", week_start)

    # 1) baseline
    b_wc, b_util, b_over, b_orders = _loads(week_start)
    baseline = Scenario(
        key="baseline", name="Baseline (as-is)",
        description="The week exactly as planned today.",
        bottleneck_wc=b_wc, bottleneck_util=b_util, overloaded_count=b_over,
        orders_planned=b_orders,
        outcome=(f"{b_wc} at {b_util:.0f}%, {b_over} machine(s) overloaded."
                 if b_over else f"On track - busiest {b_wc} at {b_util:.0f}%."))

    # 2) add a shift to the bottleneck department
    bn_dept = wcs[b_wc]["department"] if b_wc else None
    s_wc, s_util, s_over, s_orders = _loads(week_start, extra_shift_depts={bn_dept} if bn_dept else set())
    add_shift = Scenario(
        key="add_shift", name=f"Add a shift ({bn_dept})",
        description=f"Give the {bn_dept} department one extra shift this week.",
        bottleneck_wc=s_wc, bottleneck_util=s_util, overloaded_count=s_over,
        orders_planned=s_orders,
        outcome=(f"Bottleneck drops to {s_util:.0f}% ({b_over - s_over} fewer overloaded)."
                 if s_over < b_over else f"Still {s_over} overloaded - one shift is not enough."))

    # 3) defer the least-urgent orders until within capacity
    pr = prioritize_week(week_start)
    least_urgent = [o.order_id for o in sorted(pr.orders, key=lambda x: x.score)]  # lowest score first
    exclude, deferred = set(), 0
    d_wc, d_util, d_over, d_orders = b_wc, b_util, b_over, b_orders
    for oid in least_urgent:
        if d_over == 0 or deferred >= 20:
            break
        exclude.add(oid)
        deferred += 1
        d_wc, d_util, d_over, d_orders = _loads(week_start, exclude=exclude)
    defer = Scenario(
        key="defer", name="Defer least-urgent orders",
        description="Push the lowest-priority orders to a later week.",
        bottleneck_wc=d_wc, bottleneck_util=d_util, overloaded_count=d_over,
        orders_planned=d_orders,
        outcome=(f"Defer {deferred} order(s) -> bottleneck {d_util:.0f}%, {d_over} overloaded."
                 if deferred else "Nothing to defer - already within capacity."))

    if b_over == 0:
        summary = f"Week of {week_start} is already within capacity - scenarios show headroom."
    else:
        summary = (f"Week of {week_start}: baseline has {b_over} overloaded machine(s). "
                   f"Adding a shift leaves {s_over}; deferring {deferred} order(s) leaves {d_over}.")
    log.info("SCENARIOS  %s", summary)

    return ScenarioComparison(week_start=week_start.isoformat(),
                              scenarios=[baseline, add_shift, defer], summary=summary)
