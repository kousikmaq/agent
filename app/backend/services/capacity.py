"""
Capacity Analysis on the real dataset - the first fully implemented feature.

Two modes (this is where "batch processing" shows up):
  * analyze_week(week)  -> detailed load for one week (drill-down).
  * overview()          -> BULK: analyse every week of the order book in one pass.

Batch/campaign insight: if orders for the same item run together (a campaign),
they share one machine setup instead of one per order. We report the setup hours
that batching would save each week.
"""
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache

from logging_config import get_logger
from data_loader import load
from models import (ResourceLoad, Bottleneck, BatchingInsight, OrderRow, Recommendation,
                    WeekLoad, WeekSummary, OverviewResult, HeatCell, HeatRow, HeatmapResult)

log = get_logger("capacity")
ACTIVE = {"Open", "Released"}  # statuses that still need to be produced


def _alt_map() -> dict:
    """work_center -> set of alternate work centres (from all routings)."""
    alts: dict = {}
    for ops in load()["routings"].values():
        for op in ops:
            if op.get("alt_work_center"):
                alts.setdefault(op["work_center"], set()).add(op["alt_work_center"])
    return alts


def _cell_status(util: float) -> str:
    return "OVERLOADED" if util > 100 else ("TIGHT" if util >= 85 else "OK")


def _orders_in_week(week_start: date) -> list:
    d = load()
    end = week_start + timedelta(days=7)
    return [o for o in d["orders"]
            if week_start <= o["due_date"] < end and o["status"] in ACTIVE]


@lru_cache(maxsize=None)
def analyze_week(week_start: date) -> WeekLoad:
    d = load()
    wcs, items, routings = d["work_centers"], d["items"], d["routings"]
    orders = _orders_in_week(week_start)
    log.info("STEP 1/5  Capacity for week %s | active orders due = %d", week_start, len(orders))

    run_min = defaultdict(float)        # work-center -> running minutes
    setup_naive = defaultdict(float)    # one setup per order-op
    setup_batched = defaultdict(float)  # one setup per (item, op) = campaign
    seen_item_op = set()

    for o in orders:
        for op in routings.get(o["item_id"], []):
            wc = op["work_center"]
            run_min[wc] += op["run_min_per_unit"] * o["quantity"]
            setup_naive[wc] += op["setup_min"]
            key = (o["item_id"], op["op_seq"])
            if key not in seen_item_op:
                seen_item_op.add(key)
                setup_batched[wc] += op["setup_min"]
    log.info("STEP 2/5  Rolled up work onto %d work centers", len(run_min))

    resources = []
    for wc_id, wc in wcs.items():
        req = round((run_min[wc_id] + setup_naive[wc_id]) / 60.0, 1)
        avail = round(wc["weekly_capacity_hours"], 1)
        util = round(req / avail * 100, 1) if avail else 0.0
        overload = round(max(0.0, req - avail), 1)
        resources.append(ResourceLoad(
            work_center=wc_id, name=wc["name"], department=wc["department"],
            required_hours=req, available_hours=avail, utilization_pct=util,
            overload_hours=overload, status="OVERLOADED" if req > avail else "OK",
        ))
    resources.sort(key=lambda r: r.utilization_pct, reverse=True)
    log.info("STEP 3/5  Computed utilisation for %d work centers", len(resources))

    bottleneck = None
    if resources:
        top = resources[0]
        if top.utilization_pct > 100:
            msg = (f"{top.work_center} ({top.name}) is the bottleneck at {top.utilization_pct:.0f}% "
                   f"- {top.overload_hours:.0f}h over. Protect it, batch similar jobs, or offload.")
        else:
            msg = f"No overload. Busiest is {top.work_center} at {top.utilization_pct:.0f}%."
        bottleneck = Bottleneck(work_center=top.work_center, utilization_pct=top.utilization_pct,
                                overload_hours=top.overload_hours, message=msg)
    log.info("STEP 4/5  Bottleneck: %s", bottleneck.work_center if bottleneck else "none")

    naive_h = round(sum(setup_naive.values()) / 60.0, 1)
    batched_h = round(sum(setup_batched.values()) / 60.0, 1)
    saved = round(naive_h - batched_h, 1)
    batching = BatchingInsight(
        naive_setup_hours=naive_h, batched_setup_hours=batched_h, setup_hours_saved=saved,
        note=(f"Running same-item orders as one campaign this week saves {saved:.1f} setup hours "
              f"({naive_h:.1f}h -> {batched_h:.1f}h)."),
    )

    order_rows = [OrderRow(
        order_id=o["order_id"], item_id=o["item_id"],
        item_name=items.get(o["item_id"], {}).get("item_name", o["item_id"]),
        customer_id=o["customer_id"], quantity=o["quantity"],
        due_date=o["due_date"].isoformat(), priority=o["priority"], status=o["status"],
    ) for o in sorted(orders, key=lambda x: x["due_date"])]

    # Recommended actions: offload an overloaded machine onto an idle qualified backup.
    res_map = {r.work_center: r for r in resources}
    alts = _alt_map()
    recs: list[Recommendation] = []
    seen = set()
    for r in resources:
        if r.status != "OVERLOADED":
            continue
        for alt in sorted(alts.get(r.work_center, [])):
            ar = res_map.get(alt)
            if not ar or ar.utilization_pct >= 85:
                continue
            free = round(ar.available_hours - ar.required_hours, 1)
            move = round(min(r.overload_hours, max(0.0, free)), 1)
            if move >= 1 and (r.work_center, alt) not in seen:
                seen.add((r.work_center, alt))
                recs.append(Recommendation(
                    from_wc=r.work_center, to_wc=alt, hours=move,
                    text=(f"Move ~{move:.0f}h from {r.work_center} ({r.utilization_pct:.0f}%) "
                          f"to {alt} ({ar.utilization_pct:.0f}%, ~{free:.0f}h free)."),
                ))
    log.info("  Recommendations: %d offload option(s)", len(recs))

    overloaded = [r.work_center for r in resources if r.status == "OVERLOADED"]
    summary = (f"Week of {week_start}: {len(orders)} orders. "
               + (f"{len(overloaded)} overloaded: {', '.join(overloaded)}. {bottleneck.message}"
                  if overloaded else "All work centers within capacity."))
    log.info("STEP 5/5  %s", summary)

    return WeekLoad(week_start=week_start.isoformat(), orders_considered=len(orders),
                    resources=resources, bottleneck=bottleneck, batching=batching,
                    recommendations=recs, summary=summary, orders=order_rows)


def heatmap() -> HeatmapResult:
    """A work-centre x week grid of utilisation (the classic capacity view)."""
    d = load()
    log.info("HEATMAP  Building work-centre x week utilisation grid...")
    weeks = [w.isoformat() for w in d["weeks"]]
    # collect per week the utilisation of every work centre
    by_wc: dict = {}
    for w in d["weeks"]:
        wl = analyze_week(w)
        for r in wl.resources:
            by_wc.setdefault(r.work_center, {"name": r.name, "department": r.department, "cells": []})
            by_wc[r.work_center]["cells"].append(
                HeatCell(week_start=w.isoformat(), utilization_pct=r.utilization_pct,
                         status=_cell_status(r.utilization_pct)))
    # order rows by department then busiest first
    rows = [HeatRow(work_center=wc, name=v["name"], department=v["department"], cells=v["cells"])
            for wc, v in by_wc.items()]
    rows.sort(key=lambda r: (r.department, -max(c.utilization_pct for c in r.cells)))
    return HeatmapResult(weeks=weeks, rows=rows)


def overview() -> OverviewResult:
    """BULK processing: analyse every week of the order book in one pass."""
    d = load()
    log.info("BULK  Analysing all %d weeks of the order book...", len(d["weeks"]))
    summaries = []
    overloaded_weeks = 0
    for wk in d["weeks"]:
        wl = analyze_week(wk)
        total_req = round(sum(r.required_hours for r in wl.resources), 1)
        total_cap = round(sum(r.available_hours for r in wl.resources), 1)
        over = sum(1 for r in wl.resources if r.status == "OVERLOADED")
        if over:
            overloaded_weeks += 1
        bn = wl.bottleneck
        status = "OVERLOADED" if over else ("TIGHT" if bn and bn.utilization_pct >= 85 else "OK")
        summaries.append(WeekSummary(
            week_start=wk.isoformat(), orders=wl.orders_considered,
            bottleneck_wc=bn.work_center if bn else None,
            bottleneck_util=bn.utilization_pct if bn else 0.0,
            overloaded_count=over, total_required_hours=total_req,
            total_capacity_hours=total_cap, status=status,
        ))
    log.info("BULK  Done. %d of %d weeks have an overload.", overloaded_weeks, len(summaries))
    return OverviewResult(weeks=summaries, total_orders=len(d["orders"]),
                          overloaded_weeks=overloaded_weeks)


def list_weeks() -> list:
    return [w.isoformat() for w in load()["weeks"]]


_DEFAULT_WEEK: date | None = None


def default_week() -> date:
    """The most overloaded week (a useful default). Cached - the data is static."""
    global _DEFAULT_WEEK
    if _DEFAULT_WEEK is None:
        worst = max(overview().weeks, key=lambda w: w.bottleneck_util)
        _DEFAULT_WEEK = date.fromisoformat(worst.week_start)
    return _DEFAULT_WEEK
