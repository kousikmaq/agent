"""
Schedule Optimization - the flagship feature.

Given a week, take its most urgent orders and build a FEASIBLE, near-optimal
finite-capacity schedule with Google OR-Tools CP-SAT:
  * each order is a job whose operations run in routing order (precedence),
  * each operation runs on its work centre for setup + run*qty minutes,
  * a machine does one operation at a time (no overlap),
  * objective: minimise the makespan (finish everything as early as possible).

We schedule the top-N urgent orders (default 12) so the plan solves fast and the
Gantt stays readable - honestly labelled as such in the UI.
"""
import time
from datetime import date

from ortools.sat.python import cp_model

from logging_config import get_logger
from data_loader import load
from services.prioritize import prioritize_week
from models import ScheduledOp, SchedulePlan

log = get_logger("schedule")


def optimize_week(week_start: date, n: int = 12) -> SchedulePlan:
    d = load()
    items, routings = d["items"], d["routings"]
    order_by_id = {o["order_id"]: o for o in d["orders"]}

    # take the N most urgent orders for the week (ties the feature to prioritisation)
    top = prioritize_week(week_start).orders[:n]
    selected = [order_by_id[p.order_id] for p in top]
    log.info("SCHEDULE  week %s | optimising %d orders", week_start, len(selected))

    # build durations
    jobs = []  # each: list of (op_seq, work_center, duration_min)
    for o in selected:
        ops = sorted(routings.get(o["item_id"], []), key=lambda x: x["op_seq"])
        jobs.append([(op["op_seq"], op["work_center"],
                      max(1, int(round(op["setup_min"] + op["run_min_per_unit"] * o["quantity"]))))
                     for op in ops])

    horizon = sum(dur for job in jobs for (_, _, dur) in job) or 1
    model = cp_model.CpModel()
    machine_intervals: dict = {}
    all_ops = []          # (job_idx, op_seq, wc, start, end)
    job_ends = []

    for j, job in enumerate(jobs):
        prev_end = None
        last_end = None
        for (op_seq, wc, dur) in job:
            start = model.new_int_var(0, horizon, f"s_{j}_{op_seq}")
            end = model.new_int_var(0, horizon, f"e_{j}_{op_seq}")
            interval = model.new_interval_var(start, dur, end, f"i_{j}_{op_seq}")
            machine_intervals.setdefault(wc, []).append(interval)
            if prev_end is not None:
                model.add(start >= prev_end)          # precedence within the job
            prev_end = end
            last_end = end
            all_ops.append((j, op_seq, wc, start, end))
        if last_end is not None:
            job_ends.append(last_end)

    for wc, ivs in machine_intervals.items():
        model.add_no_overlap(ivs)                     # one op per machine at a time

    if not job_ends:                                  # nothing active to schedule this week
        return SchedulePlan(
            week_start=week_start.isoformat(), orders_scheduled=len(selected),
            machines=[], makespan_min=0, makespan_hours=0.0,
            status="NO_SOLUTION", objective="minimise makespan", solve_ms=0, ops=[])

    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, job_ends)
    model.minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 8
    t0 = time.time()
    status = solver.solve(model)
    solve_ms = int((time.time() - t0) * 1000)

    status_str = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE"}.get(status, "NO_SOLUTION")
    log.info("SCHEDULE  status=%s makespan=%s min solve=%dms",
             status_str, solver.value(makespan) if status_str != "NO_SOLUTION" else "-", solve_ms)

    ops_out = []
    if status_str != "NO_SOLUTION":
        for (j, op_seq, wc, start, end) in all_ops:
            s, e = solver.value(start), solver.value(end)
            ops_out.append(ScheduledOp(
                order_id=selected[j]["order_id"],
                item_name=items.get(selected[j]["item_id"], {}).get("item_name", ""),
                work_center=wc, op_seq=op_seq, start_min=s, end_min=e, duration_min=e - s,
            ))
        makespan_min = int(solver.value(makespan))
    else:
        makespan_min = 0

    machines = sorted(machine_intervals.keys())
    return SchedulePlan(
        week_start=week_start.isoformat(), orders_scheduled=len(selected),
        machines=machines, makespan_min=makespan_min,
        makespan_hours=round(makespan_min / 60.0, 1), status=status_str,
        objective="minimise makespan", solve_ms=solve_ms, ops=ops_out,
    )
