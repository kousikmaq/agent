"""Weekly Master Plan.

Composes the seven features into one proactive baseline plan for the week, generated once
(cached by data version) and shown on app open. It only READS the existing feature functions
(capacity, scheduler, demand, risk, reorder) - it does not change them - so no feature is
affected and there are no inconsistencies.

Factors: demand forecast, capacity vs workload, machines + maintenance, workforce (in the
scheduler), materials to re-order, due-date risk and machine downtime risk.
"""
from __future__ import annotations

import json
import os
import re

import pandas as pd

from app.analytics._util import planning_now
from app.analytics.capacity import capacity_analysis
from app.actions.reorder_action import reorder_recommendations
from app.cache.semantic_cache import _data_version
from app.config import EXPORTS_DIR
from app.ml import registry
from app.optimization.scheduler import optimize_schedule

HORIZON_DAYS = 7
MAX_ORDERS = 15

_CACHE: dict = {}
_PLAN_DIR = os.path.join(EXPORTS_DIR, "plan_cache")
os.makedirs(_PLAN_DIR, exist_ok=True)


def _disk_path(scenario: str) -> str:
    # Sanitise scenario so it can never escape the cache directory (no path traversal).
    safe = re.sub(r"[^a-z_]", "", (scenario or "").lower())[:24] or "default"
    return os.path.join(_PLAN_DIR, f"plan_{_data_version()}_{safe}.json")


def _load_disk(scenario: str) -> dict | None:
    path = _disk_path(scenario)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 - a corrupt cache just triggers a rebuild
        return None


def _save_disk(scenario: str, plan: dict) -> None:
    try:
        with open(_disk_path(scenario), "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
    except Exception:  # noqa: BLE001 - never fail a request on a cache-write issue
        pass



def build_weekly_plan(scenario: str = "min_risk") -> dict:
    now = planning_now()
    week_start = now.strftime("%d-%m-%Y")
    week_end = (now + pd.Timedelta(days=HORIZON_DAYS)).strftime("%d-%m-%Y")

    cap = capacity_analysis(HORIZON_DAYS)
    plan = optimize_schedule(scenario, max_orders=MAX_ORDERS)
    k = plan.get("kpis", {})

    # optional model-backed pieces (degrade gracefully if a model is missing)
    try:
        demand = registry.forecast_demand(HORIZON_DAYS).get("products", [])
    except Exception:  # noqa: BLE001
        demand = []
    try:
        stockout = registry.demand_stockout_risk(top_n=5).get("at_risk", [])
    except Exception:  # noqa: BLE001
        stockout = []
    try:
        due = registry.predict_order_due_risk(top_n=100)
    except Exception:  # noqa: BLE001
        due = {"orders_missing_due": 0, "at_risk_orders": []}
    try:
        downtime = registry.predict_downtime_latest().get("machines_at_risk", [])
    except Exception:  # noqa: BLE001
        downtime = []
    reorder = reorder_recommendations(HORIZON_DAYS).get("recommendations", [])

    total_req = cap.get("total_required_hours", 0.0)
    total_avail = cap.get("total_available_hours", 0.0)
    workload_coverage = round(min(100.0, (total_avail / total_req * 100.0) if total_req else 100.0), 1)
    constrained = cap.get("constrained_machines", [])

    misses = [o for o in due.get("at_risk_orders", []) if o.get("will_miss_due")]

    headline = (
        f"Week of {week_start}: {plan.get('scheduled_orders', 0)} orders planned "
        f"({k.get('orders_on_time', 0)} on-time), {cap.get('overall_utilization_pct', 0):.0f}% capacity"
        + (f", {len(constrained)} machine(s) constrained" if constrained else "")
        + (f", {len(downtime)} at breakdown risk" if downtime else "")
    )

    return {
        "planning_week": {"start": week_start, "end": week_end},
        "scenario": scenario,
        "headline": headline,
        "kpis": {
            "orders_planned": plan.get("scheduled_orders", 0),
            "operations": plan.get("operations_scheduled", 0),
            "orders_on_time": k.get("orders_on_time", 0),
            "makespan_hours": k.get("makespan_hours"),
            "total_tardiness_hours": k.get("total_tardiness_hours"),
            "energy_cost_inr": k.get("total_energy_cost_inr"),
            "capacity_utilization_pct": round(cap.get("overall_utilization_pct", 0.0), 1),
            "workload_coverage_pct": workload_coverage,
        },
        "capacity": {
            "verdict": cap.get("verdict"),
            "constrained_machines": constrained,
            "expected_shortfall_hours": round(cap.get("total_expected_shortfall_hours", 0.0), 1),
            "per_machine": cap.get("per_machine", []),
        },
        "demand": {
            "top": [
                {"product_id": p["product_id"], "units": p["forecast_units_total"],
                 "low": p["p10_units_total"], "high": p["p90_units_total"], "revenue": p["forecast_revenue"]}
                for p in demand[:5]
            ],
            "stockout_risk": stockout,
        },
        "risk": {
            "orders_missing_due": len(misses),
            "at_risk_orders": misses[:5],
            "machines_at_risk": downtime,
        },
        "materials_to_reorder": [
            {"material_id": r["material_id"], "name": r["material_name"],
             "suggested_quantity": r["suggested_quantity"], "estimated_cost_inr": r["estimated_cost_inr"]}
            for r in reorder
        ],
        "schedule": plan.get("assignments", [])[:15],
    }


def get_weekly_plan(scenario: str = "min_risk", force: bool = False) -> dict:
    """Weekly plan, built once and persisted. It is reused from memory, then from disk, and is
    only rebuilt when the data changes or the user explicitly regenerates (force=True)."""
    from app.logging_config import log
    key = (_data_version(), scenario)

    if not force:
        if key in _CACHE:
            log.info("PLAN   cache hit (memory, scenario=%s)", scenario)
            return {**_CACHE[key], "cached": True}
        disk = _load_disk(scenario)
        if disk is not None:
            log.info("PLAN   cache hit (disk, scenario=%s)", scenario)
            _CACHE[key] = disk
            return {**disk, "cached": True}

    log.info("PLAN   building weekly master plan (scenario=%s) - running OR-Tools + models...", scenario)
    plan = build_weekly_plan(scenario)
    log.info("PLAN   done: %d orders, %d operations, %d materials to re-order",
             plan["kpis"]["orders_planned"], plan["kpis"]["operations"], len(plan["materials_to_reorder"]))
    _CACHE[key] = plan
    _save_disk(scenario, plan)
    return {**plan, "cached": False}
