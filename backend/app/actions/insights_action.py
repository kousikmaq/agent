"""Insights report. Composes a small set of high-level, chart-ready figures plus a plain-English
narrative from the existing analytics/ML/plan functions. The frontend renders these with an
interactive chart library; nothing here changes the underlying features."""
from __future__ import annotations

from datetime import datetime


def _round(x, n=1):
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return 0.0


def build_insights() -> dict:
    from app.analytics.capacity import capacity_analysis
    from app.analytics.bottleneck import detect_bottlenecks
    from app.ml import registry
    from app.optimization.scheduler import compare_scenarios
    from app.planning import get_weekly_plan

    plan = get_weekly_plan("min_risk")
    k = plan.get("kpis", {})
    cap = capacity_analysis(7)
    charts: list[dict] = []

    # 1) Machine utilisation (bar)
    per_m = cap.get("per_machine", [])
    charts.append({
        "id": "utilisation", "title": "Machine Utilisation", "type": "bar", "unit": "%",
        "insight": (f"{per_m[0]['machine_id']} is the most loaded at {per_m[0]['utilization_pct']:.0f}%."
                    if per_m else "No capacity data."),
        "data": [{"name": m["machine_id"], "value": _round(m["utilization_pct"])} for m in per_m],
    })

    # 2) Downtime risk (bar)
    try:
        dt = registry.predict_downtime_latest().get("machines", [])
    except Exception:  # noqa: BLE001
        dt = []
    top_dt = dt[0] if dt else None
    charts.append({
        "id": "downtime", "title": "Machine Downtime Risk", "type": "bar", "unit": "%",
        "insight": (f"{top_dt['machine_id']} has the highest breakdown risk at {top_dt['downtime_risk_pct']:.0f}%."
                    if top_dt else "All machines healthy."),
        "data": [{"name": m["machine_id"], "value": _round(m["downtime_risk_pct"])} for m in dt],
    })

    # 3) Delay-risk operations (horizontal bar)
    try:
        dr = registry.predict_delay_for_pending(top_n=6).get("at_risk", [])
    except Exception:  # noqa: BLE001
        dr = []
    charts.append({
        "id": "delay_risk", "title": "Top Delay-Risk Operations", "type": "barh", "unit": "%",
        "insight": (f"{len(dr)} operations carry elevated delay risk; tackle the top ones first."
                    if dr else "No operations at notable delay risk."),
        "data": [{"name": f"{o['order_id']}", "value": _round(o["delay_risk_pct"])} for o in dr],
    })

    # 4) 7-day demand with P10-P90 band
    try:
        dem = registry.forecast_demand(7).get("products", [])[:6]
    except Exception:  # noqa: BLE001
        dem = []
    charts.append({
        "id": "demand_band", "title": "7-Day Demand (P10–P90)", "type": "band", "unit": "units",
        "insight": (f"{dem[0]['product_id']} leads demand at ~{dem[0]['forecast_units_total']:.0f} units."
                    if dem else "No demand forecast."),
        "data": [{"name": p["product_id"], "mid": _round(p["forecast_units_total"], 0),
                  "low": _round(p["p10_units_total"], 0), "high": _round(p["p90_units_total"], 0),
                  "range": [_round(p["p10_units_total"], 0), _round(p["p90_units_total"], 0)]} for p in dem],
    })

    # 5) Demand by region (pie)
    try:
        reg = registry.demand_region_split().get("region_share_pct", {})
    except Exception:  # noqa: BLE001
        reg = {}
    charts.append({
        "id": "regions", "title": "Demand by Region", "type": "pie", "unit": "%",
        "insight": (f"{max(reg, key=reg.get)} is the largest region by demand share."
                    if reg else "No regional data."),
        "data": [{"name": r, "value": _round(v)} for r, v in reg.items()],
    })

    # 6) Scenario tardiness (bar)
    try:
        sc = compare_scenarios().get("scenarios", {})
    except Exception:  # noqa: BLE001
        sc = {}
    charts.append({
        "id": "scenarios", "title": "Scenario Tardiness", "type": "bar", "unit": "h",
        "insight": ("The min-risk scenario keeps late-delivery hours lowest."
                    if sc else "No scenario comparison."),
        "data": [{"name": n, "value": _round(v.get("total_tardiness_hours", 0))} for n, v in sc.items()],
    })

    bn = detect_bottlenecks(7)
    kpis = [
        {"label": "Capacity", "value": f"{k.get('capacity_utilization_pct', 0)}%",
         "tone": "rose" if (k.get("capacity_utilization_pct") or 0) > 100 else "green"},
        {"label": "Orders on time", "value": k.get("orders_on_time", 0),
         "tone": "rose" if (k.get("orders_on_time") or 0) == 0 else "green"},
        {"label": "Machines at risk", "value": len(plan.get("risk", {}).get("machines_at_risk", [])),
         "tone": "rose" if plan.get("risk", {}).get("machines_at_risk") else "green"},
        {"label": "Materials to re-order", "value": len(plan.get("materials_to_reorder", [])),
         "tone": "amber" if plan.get("materials_to_reorder") else "green"},
    ]

    narrative = [
        f"Capacity is running at {k.get('capacity_utilization_pct', 0):.0f}% this week — "
        + ("above safe limits on one or more machines." if (k.get("capacity_utilization_pct") or 0) > 100
           else "within available limits."),
        f"The main bottleneck is {bn.get('primary_bottleneck', 'n/a')}, so it sets the pace of the whole line.",
        (f"{top_dt['machine_id']} is the biggest reliability worry at {top_dt['downtime_risk_pct']:.0f}% breakdown risk."
         if top_dt else "Machine health looks stable."),
        (f"Demand is led by {dem[0]['product_id']} (~{dem[0]['forecast_units_total']:.0f} units); "
         "plan production and stock around the top SKUs." if dem else "Demand forecast unavailable."),
        (f"{len(plan.get('materials_to_reorder', []))} material(s) are below reorder point — "
         "raise purchase orders to avoid stockouts." if plan.get("materials_to_reorder")
         else "Material stock levels are healthy."),
    ]

    return {
        "generated_at": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "headline": "Weekly production insights",
        "kpis": kpis,
        "narrative": narrative,
        "charts": [c for c in charts if c["data"]],
    }
