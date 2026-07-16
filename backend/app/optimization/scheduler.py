"""Flexible job-shop scheduler (OR-Tools CP-SAT).

Schedules the operations of the most urgent pending orders across eligible machines,
respecting operation precedence and machine non-overlap. Supports 3 planning scenarios:

  * max_throughput -> minimise makespan (finish everything as early as possible)
  * min_risk       -> minimise total tardiness vs due dates (protect delivery dates)
  * min_cost       -> minimise total machine energy cost (favour efficient machines)

Returns a JSON-serializable plan with the assignment, timings and scenario KPIs.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
from ortools.sat.python import cp_model

from app import data_access as da
from app.analytics._util import planning_now

ENERGY_PRICE_INR_PER_KWH = 8.0
SCENARIOS = ("max_throughput", "min_risk", "min_cost")


def _order_selection(max_orders: int) -> pd.DataFrame:
    orders = da.orders()
    pend = orders[orders["status"].isin(["Open", "Scheduled"])].copy()
    now = planning_now()
    pend["days_to_due"] = (pend["due_date"] - now).dt.days
    return pend.sort_values(["priority", "days_to_due"]).head(max_orders)


def optimize_schedule(scenario: str = "min_risk", max_orders: int = 12,
                      time_limit_s: float = 10.0) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")

    ops_dim = da.operations().sort_values("sequence")
    machines = da.machines()
    energy_by_machine = dict(zip(machines["machine_id"], machines["hourly_energy_kwh"]))
    std_minutes = dict(zip(ops_dim["operation_id"], ops_dim["standard_minutes"]))
    eligible = dict(zip(ops_dim["operation_id"], ops_dim["eligible_machine_ids"].str.split(";")))
    op_sequence = list(ops_dim["operation_id"])

    selected = _order_selection(max_orders)
    if selected.empty:
        return {"scenario": scenario, "scheduled_orders": 0, "assignments": [], "kpis": {}}

    now = planning_now()
    model = cp_model.CpModel()

    # upper bound on the schedule length
    horizon = 0
    proc = {}       # (order, op) -> processing minutes
    due_min = {}    # order -> due in minutes from now
    for _, order in selected.iterrows():
        size_factor = min(3.0, max(1.0, order["order_quantity"] / 5000.0))
        due_min[order["order_id"]] = max(0, int((order["due_date"] - now).total_seconds() // 60))
        for op in op_sequence:
            p = int(round(std_minutes[op] * size_factor))
            proc[(order["order_id"], op)] = p
            horizon += p

    starts: dict = {}
    ends: dict = {}
    presence: dict = {}                       # (order, op, machine) -> BoolVar
    machine_intervals: dict[str, list] = {m: [] for m in machines["machine_id"]}
    cost_terms: list = []
    all_ends: list = []
    order_last_end: dict[str, object] = {}

    for _, order in selected.iterrows():
        oid = order["order_id"]
        prev_end = None
        for op in op_sequence:
            p = proc[(oid, op)]
            start = model.NewIntVar(0, horizon, f"s_{oid}_{op}")
            end = model.NewIntVar(0, horizon, f"e_{oid}_{op}")
            model.Add(end == start + p)
            starts[(oid, op)] = start
            ends[(oid, op)] = end
            all_ends.append(end)

            presences = []
            for m in eligible[op]:
                pres = model.NewBoolVar(f"x_{oid}_{op}_{m}")
                interval = model.NewOptionalIntervalVar(start, p, end, pres, f"i_{oid}_{op}_{m}")
                machine_intervals[m].append(interval)
                presence[(oid, op, m)] = pres
                presences.append(pres)
                cost = int(round((p / 60.0) * energy_by_machine[m] * ENERGY_PRICE_INR_PER_KWH))
                cost_terms.append((pres, cost))
            model.AddExactlyOne(presences)

            if prev_end is not None:
                model.Add(start >= prev_end)          # operation precedence within order
            prev_end = end
        order_last_end[oid] = prev_end

    for m, intervals in machine_intervals.items():
        if intervals:
            model.AddNoOverlap(intervals)             # a machine runs one op at a time

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
            chosen = next(m for m in eligible[op] if solver.Value(presence[(oid, op, m)]) == 1)
            energy_cost = int(round(((e - s) / 60.0) * energy_by_machine[chosen] * ENERGY_PRICE_INR_PER_KWH))
            total_cost += energy_cost
            assignments.append({
                "order_id": oid,
                "operation_id": op,
                "machine_id": chosen,
                "start": (now + timedelta(minutes=int(s))).strftime("%d-%m-%Y %H:%M:%S"),
                "end": (now + timedelta(minutes=int(e))).strftime("%d-%m-%Y %H:%M:%S"),
                "duration_min": int(e - s),
                "energy_cost_inr": energy_cost,
            })

    kpis = {
        "makespan_hours": round(solver.Value(makespan) / 60.0, 1),
        "total_tardiness_hours": round(solver.Value(total_tardiness) / 60.0, 1),
        "total_energy_cost_inr": int(total_cost),
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
