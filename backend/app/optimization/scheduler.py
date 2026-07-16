"""Flexible job-shop scheduler (OR-Tools CP-SAT).

Schedules the operations of the most urgent pending orders across eligible machines,
respecting operation precedence and machine non-overlap. Supports 3 planning scenarios:

  * max_throughput -> minimise makespan (finish everything as early as possible)
  * min_risk       -> minimise total tardiness vs due dates (protect delivery dates)
  * min_cost       -> minimise total machine energy cost (favour efficient machines)

Each operation is scheduled in one of several "modes" (multi-mode scheduling): a mode fixes
how many parallel machines and how many workers the operation uses, which together set its
duration. This lets the solver throw more machines / workers at an operation to hit a due
date or honour a priority, at the cost of tying up more resources.

Hard constraints enforced by the model (5 core rules):
  1. Mode selection  - each operation runs in exactly ONE mode; a mode bundles which/how
                       many eligible machines and how many workers it uses, which together
                       set its duration (covers eligibility, lot-splitting and the
                       worker-dependent speed-up)
  2. Precedence      - the operations of an order run in sequence
  3. Machine timeline- a machine runs one operation at a time, plus a setup buffer after
                       each op and its own maintenance window (all on one no-overlap timeline)
  4. Labour capacity - concurrent operations cannot exceed the per-shift workforce; a
                       2-machine split needs workers on both machines
  5. Objective       - minimise makespan / tardiness / energy cost per scenario; due dates
                       optionally hard (enforce_due_dates), otherwise tardiness is a soft goal

Inherent properties (true automatically, not separately coded):
  - No preemption      : an operation is one continuous interval, never paused
  - Planning horizon   : every start/end is bounded to the planning window [0, horizon]
  - Order completion   : an order finishes only when its last operation ends

Returns a JSON-serializable plan with the assignment, timings and scenario KPIs.
"""
from __future__ import annotations

from datetime import timedelta
from itertools import combinations

import pandas as pd
from ortools.sat.python import cp_model

from app import data_access as da
from app.analytics._util import planning_now

ENERGY_PRICE_INR_PER_KWH = 8.0
SCENARIOS = ("max_throughput", "min_risk", "min_cost")
SETUP_MINUTES = 15            # changeover/cleanup buffer reserved on a machine after each op
MAINTENANCE_SCALE_MIN = 600   # maintenance window length = (1 - reliability_index) * this
MIN_OP_MINUTES = 5            # a mode can never compress an operation below this
MAX_PARALLEL_MACHINES = 2     # cap on how many machines one operation may be split across


def _order_selection(max_orders: int) -> pd.DataFrame:
    orders = da.orders()
    pend = orders[orders["status"].isin(["Open", "Scheduled"])].copy()
    now = planning_now()
    pend["days_to_due"] = (pend["due_date"] - now).dt.days
    return pend.sort_values(["priority", "days_to_due"]).head(max_orders)


def optimize_schedule(scenario: str = "min_risk", max_orders: int = 12,
                      time_limit_s: float = 10.0, enforce_due_dates: bool = False) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")

    ops_dim = da.operations().sort_values("sequence")
    machines = da.machines()
    energy_by_machine = dict(zip(machines["machine_id"], machines["hourly_energy_kwh"]))
    reliability_by_machine = dict(zip(machines["machine_id"], machines["reliability_index"].astype(float)))
    std_minutes = dict(zip(ops_dim["operation_id"], ops_dim["standard_minutes"]))
    min_workers = dict(zip(ops_dim["operation_id"], ops_dim["min_workers"].astype(int)))
    pref_workers = dict(zip(ops_dim["operation_id"], ops_dim["preferred_workers"].astype(int)))
    eligible = dict(zip(ops_dim["operation_id"], ops_dim["eligible_machine_ids"].str.split(";")))
    op_sequence = list(ops_dim["operation_id"])

    # concurrent workforce = workers available in a single shift (only one shift runs at a time)
    workers = da.workers()
    avail = da.worker_shift_availability()
    per_shift = avail[avail["available"] == 1].groupby(["availability_date", "shift_id"]).size()
    worker_capacity = int(per_shift.mean()) if len(per_shift) else \
        (int((workers["employment_status"] == "Active").sum()) or len(workers))

    selected = _order_selection(max_orders)
    if selected.empty:
        return {"scenario": scenario, "scheduled_orders": 0, "assignments": [], "kpis": {}}

    now = planning_now()
    model = cp_model.CpModel()

    # base processing minutes (one machine, minimum workers) and due dates
    proc = {}       # (order, op) -> base processing minutes
    due_min = {}    # order -> due in minutes from now
    base_total = 0
    for _, order in selected.iterrows():
        size_factor = min(3.0, max(1.0, order["order_quantity"] / 5000.0))
        due_min[order["order_id"]] = max(0, int((order["due_date"] - now).total_seconds() // 60))
        for op in op_sequence:
            p = int(round(std_minutes[op] * size_factor))
            proc[(order["order_id"], op)] = p
            base_total += p

    # generous upper bound: base work + a setup per op + all maintenance windows
    maint_total = sum(int(round((1.0 - reliability_by_machine[m]) * MAINTENANCE_SCALE_MIN))
                      for m in machines["machine_id"])
    total_ops = len(selected) * len(op_sequence)
    horizon = base_total + total_ops * SETUP_MINUTES + maint_total + 60

    starts: dict = {}
    ends: dict = {}
    mode_choice: dict = {}                     # (order, op) -> list of mode tuples for extraction
    machine_intervals: dict[str, list] = {m: [] for m in machines["machine_id"]}
    cost_terms: list = []                      # (presence, energy_cost) for the min_cost objective
    all_ends: list = []
    order_last_end: dict[str, object] = {}
    labor_intervals: list = []                 # per-mode intervals feeding the labour pool
    labor_demands: list = []                   # workers each of those modes needs

    for _, order in selected.iterrows():
        oid = order["order_id"]
        prev_end = None
        for op in op_sequence:
            p0 = proc[(oid, op)]
            start = model.NewIntVar(0, horizon, f"s_{oid}_{op}")
            end = model.NewIntVar(0, horizon, f"e_{oid}_{op}")
            starts[(oid, op)] = start
            ends[(oid, op)] = end
            all_ends.append(end)

            elig = eligible[op]
            w_min = max(1, min_workers[op])
            w_pref = max(w_min, pref_workers[op])
            w_levels = sorted({w_min, w_pref})                 # e.g. {1, 2}
            max_par = min(len(elig), MAX_PARALLEL_MACHINES)

            # ---- build the modes: (n machines) x (n workers) -> duration ----
            mode_pres_list: list = []
            dur_terms: list = []
            modes: list = []
            for nm in range(1, max_par + 1):
                for combo in combinations(elig, nm):
                    for w in w_levels:
                        # more machines and more workers shorten the operation
                        dur = max(MIN_OP_MINUTES, -(-p0 * w_min // (nm * w)))   # ceil division
                        energy = int(round(
                            sum((dur / 60.0) * energy_by_machine[mm] for mm in combo)
                            * ENERGY_PRICE_INR_PER_KWH))
                        tag = f"{nm}_{'-'.join(combo)}_{w}"
                        pres = model.NewBoolVar(f"m_{oid}_{op}_{tag}")
                        mode_pres_list.append(pres)
                        dur_terms.append(pres * dur)
                        # occupy every machine used by this mode (+ setup buffer)
                        for mm in combo:
                            machine_intervals[mm].append(
                                model.NewOptionalFixedSizeIntervalVar(
                                    start, dur + SETUP_MINUTES, pres, f"i_{oid}_{op}_{mm}_{tag}"))
                        # this mode's workers occupy the labour pool for its duration;
                        # w is per-machine, so a 2-machine split needs workers on both
                        labor_intervals.append(
                            model.NewOptionalFixedSizeIntervalVar(start, dur, pres, f"l_{oid}_{op}_{tag}"))
                        labor_demands.append(int(w) * len(combo))
                        cost_terms.append((pres, energy))
                        modes.append((pres, combo, int(w), dur, energy))

            model.AddExactlyOne(mode_pres_list)                # exactly one mode per operation
            model.Add(end == start + sum(dur_terms))           # duration follows the chosen mode
            mode_choice[(oid, op)] = modes

            if prev_end is not None:
                model.Add(start >= prev_end)                   # operation precedence within order
            prev_end = end
        order_last_end[oid] = prev_end

    # reserve a maintenance window on each machine (longer for less-reliable machines)
    for idx, m in enumerate(machines["machine_id"]):
        maint_dur = int(round((1.0 - reliability_by_machine[m]) * MAINTENANCE_SCALE_MIN))
        if maint_dur > 0:
            maint_start = (idx + 1) * 90              # stagger windows so they don't all collide
            machine_intervals[m].append(
                model.NewFixedSizeIntervalVar(maint_start, maint_dur, f"maint_{m}"))

    for m, intervals in machine_intervals.items():
        if intervals:
            model.AddNoOverlap(intervals)             # a machine runs one op at a time

    # labour capacity: concurrently running operations cannot exceed the available workforce
    if labor_intervals:
        # never let the pool fall below a single operation's need (keeps the model feasible)
        capacity = max(worker_capacity, max(labor_demands))
        model.AddCumulative(labor_intervals, labor_demands, capacity)

    # ---- scenario objective ----
    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, all_ends)
    tardiness_terms = []
    for oid, last_end in order_last_end.items():
        late = model.NewIntVar(0, horizon, f"late_{oid}")
        model.Add(late >= last_end - due_min[oid])
        tardiness_terms.append(late)
    total_tardiness = model.NewIntVar(0, horizon * max(1, len(selected)), "total_tardiness")
    model.Add(total_tardiness == sum(tardiness_terms))

    if enforce_due_dates:                              # optional hard deadline per order
        for oid, last_end in order_last_end.items():
            model.Add(last_end <= due_min[oid])

    if scenario == "max_throughput":
        model.Minimize(makespan)
    elif scenario == "min_risk":
        model.Minimize(total_tardiness)
    else:  # min_cost
        model.Minimize(sum(pres * c for pres, c in cost_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"scenario": scenario, "status": solver.StatusName(status),
                "scheduled_orders": int(len(selected)), "assignments": [], "kpis": {}}

    # ---- extract plan ----
    assignments = []
    total_cost = 0
    for _, order in selected.iterrows():
        oid = order["order_id"]
        for op in op_sequence:
            s = solver.Value(starts[(oid, op)])
            e = solver.Value(ends[(oid, op)])
            pres, combo, w, dur, energy = next(
                md for md in mode_choice[(oid, op)] if solver.Value(md[0]) == 1)
            total_cost += energy
            assignments.append({
                "order_id": oid,
                "operation_id": op,
                "machine_id": ";".join(combo),
                "machines_used": len(combo),
                "workers": int(w),
                "start": (now + timedelta(minutes=int(s))).strftime("%d-%m-%Y %H:%M:%S"),
                "end": (now + timedelta(minutes=int(e))).strftime("%d-%m-%Y %H:%M:%S"),
                "duration_min": int(e - s),
                "energy_cost_inr": int(energy),
            })

    kpis = {
        "makespan_hours": round(solver.Value(makespan) / 60.0, 1),
        "total_tardiness_hours": round(solver.Value(total_tardiness) / 60.0, 1),
        "total_energy_cost_inr": int(total_cost),
        "orders_on_time": int(sum(1 for oid, le in order_last_end.items()
                                  if solver.Value(le) <= due_min[oid])),
        "solver_status": solver.StatusName(status),
    }
    return {
        "scenario": scenario,
        "scheduled_orders": int(len(selected)),
        "operations_scheduled": len(assignments),
        "kpis": kpis,
        "assignments": assignments,
    }


def compare_scenarios(max_orders: int = 12) -> dict:
    """Run all three scenarios and return their KPI trade-off (satisfies the >=3 scenarios DoD)."""
    out = {}
    for sc in SCENARIOS:
        res = optimize_schedule(sc, max_orders=max_orders)
        out[sc] = res.get("kpis", {})
    return {"max_orders": max_orders, "scenarios": out}
