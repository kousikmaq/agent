"""
Resource Allocation - move work off overloaded machines onto qualified idle
backups, then show the before/after balance.

Only work that *can* move is moved: an operation is movable only if its routing
lists an alternate work centre. We offload greedily to the most-free alternate,
never pushing a target machine over its own capacity.
"""
from collections import defaultdict
from datetime import date, timedelta

from logging_config import get_logger
from data_loader import load
from models import AllocationMove, AllocationState, AllocationResult

log = get_logger("allocate")
ACTIVE = {"Open", "Released"}


def allocate_week(week_start: date) -> AllocationResult:
    d = load()
    wcs = d["work_centers"]
    routings = d["routings"]
    end = week_start + timedelta(days=7)
    orders = [o for o in d["orders"]
              if week_start <= o["due_date"] < end and o["status"] in ACTIVE]
    log.info("ALLOCATE  week %s | orders %d", week_start, len(orders))

    # roll up load per work centre, and movable minutes per (source -> alternate)
    load_min: dict = defaultdict(float)
    movable: dict = defaultdict(float)   # (src, alt) -> minutes that could move
    for o in orders:
        for op in routings.get(o["item_id"], []):
            m = op["setup_min"] + op["run_min_per_unit"] * o["quantity"]
            load_min[op["work_center"]] += m
            if op.get("alt_work_center"):
                movable[(op["work_center"], op["alt_work_center"])] += m

    avail = {wc: wcs[wc]["weekly_capacity_hours"] for wc in wcs}
    cur = {wc: round(load_min.get(wc, 0.0) / 60.0, 3) for wc in wcs}   # current hours (mutated)
    before = dict(cur)
    movable_h = {k: v / 60.0 for k, v in movable.items()}

    def util(wc, hours):
        return round(hours / avail[wc] * 100, 1) if avail[wc] else 0.0

    overloads_before = sum(1 for wc in wcs if cur[wc] > avail[wc])

    moves: list[AllocationMove] = []
    hours_moved = 0.0
    # tackle the most overloaded machines first
    for wc in sorted(wcs, key=lambda w: cur[w] - avail[w], reverse=True):
        guard = 0
        while cur[wc] > avail[wc] and guard < 20:
            guard += 1
            overload = cur[wc] - avail[wc]
            # best alternate = the one with the most free capacity and movable work
            best = None
            for (src, alt), mv in movable_h.items():
                if src != wc or mv <= 0.05:
                    continue
                free = avail[alt] - cur[alt]
                if free <= 0.05:
                    continue
                move_h = round(min(overload, mv, free), 1)
                if move_h >= 1 and (best is None or free > best[1]):
                    best = (alt, free, move_h)
            if not best:
                break
            alt, _free, move_h = best
            cur[wc] -= move_h
            cur[alt] += move_h
            movable_h[(wc, alt)] -= move_h
            hours_moved += move_h
            moves.append(AllocationMove(
                from_wc=wc, to_wc=alt, hours=move_h,
                note=(f"Move ~{move_h:.0f}h of alternate-eligible work from {wc} "
                      f"to {alt} (now {util(alt, cur[alt]):.0f}%)."),
            ))

    overloads_after = sum(1 for wc in wcs if cur[wc] > avail[wc])
    hours_moved = round(hours_moved, 1)

    # report machines that changed (source or target)
    affected = {m.from_wc for m in moves} | {m.to_wc for m in moves}
    if not affected:
        affected = {wc for wc in wcs if before[wc] > avail[wc]}
    states = []
    for wc in sorted(affected):
        ub, ua = util(wc, before[wc]), util(wc, cur[wc])
        states.append(AllocationState(
            work_center=wc, name=wcs[wc]["name"],
            util_before=ub, util_after=ua,
            status_before="OVERLOADED" if before[wc] > avail[wc] else "OK",
            status_after="OVERLOADED" if cur[wc] > avail[wc] else "OK",
        ))

    if overloads_before == 0:
        summary = "No machine is overloaded this week - no reallocation needed."
    else:
        resolved = overloads_before - overloads_after
        summary = (f"Moved {hours_moved:.0f}h of work. Cleared {resolved} of {overloads_before} "
                   f"overloaded machine(s); {overloads_after} still need attention "
                   f"(overtime, outsourcing or deferral).")
    log.info("ALLOCATE  %s", summary)

    return AllocationResult(
        week_start=week_start.isoformat(), orders_considered=len(orders),
        hours_moved=hours_moved, overloads_before=overloads_before,
        overloads_after=overloads_after, moves=moves, states=states, summary=summary,
    )
