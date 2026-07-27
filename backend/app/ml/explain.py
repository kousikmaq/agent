"""ML -> language layer. Turns raw model outputs into concise, human-readable insight
objects ({headline, details, recommended_actions}). Deterministic and LLM-free, so the
system produces clear language on its own; the LLM agents can further refine the tone."""
from __future__ import annotations

from app.ml import registry


def _pct(x: float) -> str:
    return f"{x:.0f}%"


def explain_delay_risk(top_n: int = 5) -> dict:
    res = registry.predict_delay_for_pending(top_n=top_n)
    at_risk = res.get("at_risk", [])
    high = [r for r in at_risk if r["delay_risk_pct"] >= 50.0]
    dist = res.get("predicted_distribution", {})
    try:
        due = registry.predict_order_due_risk(top_n=top_n)
        misses = due.get("orders_missing_due", 0)
    except Exception:  # noqa: BLE001
        due, misses = {"at_risk_orders": []}, 0

    headline = (
        f"{len(high)} pending operation(s) at high delay risk; {misses} order(s) predicted to miss due date"
        if high else "No pending operation is at high delay risk right now"
    )
    details = [
        f"{r['order_id']}/{r['operation_id']} on {r['machine_id']}: {r['delay_risk_pct']:.0f}% risk"
        + (f", ~{r['expected_delay_days']:.1f} days late" if r.get("expected_delay_days") is not None else "")
        + (f" (worst case {r['p90_delay_hours']:.0f}h)" if r.get("p90_delay_hours") is not None else "")
        + f" - cause: {r.get('likely_cause', 'n/a')}"
        for r in at_risk
    ]
    for o in due.get("at_risk_orders", []):
        if o.get("will_miss_due"):
            details.append(f"Order {o['order_id']} will miss {o['due_date']} by {o['days_over']:.1f} days")
    actions = []
    if high or misses:
        actions.append("Email an at-risk-orders alert to operations")
        actions.append("Re-sequence or reassign the highest-risk operations to a faster/idle machine")
    return {
        "type": "delay_risk",
        "headline": headline,
        "predicted_distribution": dist,
        "details": details,
        "recommended_actions": actions,
    }


def explain_downtime() -> dict:
    res = registry.predict_downtime_latest()
    machines = res.get("machines", [])
    at_risk = res.get("machines_at_risk", [])
    headline = (
        f"{len(at_risk)} machine(s) show sensor signatures of imminent downtime: {', '.join(at_risk)}"
        if at_risk else "All machines look healthy on the latest sensor readings"
    )
    details = [
        f"{m['machine_id']}: {m['downtime_risk_pct']:.0f}% risk, health {m['health_index']:.0f}/100"
        + (f", fault: {m['failure_type']}" if m.get("failure_type") not in (None, "None") else "")
        + (" -- ALERT" if m["alert"] else "")
        for m in machines
    ]
    actions = []
    if at_risk:
        actions.append(f"Raise a maintenance alert for {', '.join(at_risk)}")
        actions.append("Shift critical jobs off the at-risk machine(s) to an eligible alternative")
    return {
        "type": "downtime",
        "headline": headline,
        "details": details,
        "recommended_actions": actions,
    }


def explain_demand(horizon_days: int = 7, top_n: int = 5) -> dict:
    res = registry.forecast_demand(horizon_days=horizon_days)
    products = res.get("products", [])[:top_n]
    try:
        at_risk = registry.demand_stockout_risk(top_n=top_n).get("at_risk", [])
    except Exception:  # noqa: BLE001
        at_risk = []
    headline = (
        f"Top {horizon_days}-day demand: "
        + ", ".join(f"{p['product_id']} ({p['forecast_units_total']:.0f})" for p in products[:3])
        + (f"; stockout risk: {', '.join(at_risk[:3])}" if at_risk else "")
        if products else "No demand forecast available"
    )
    details = [
        f"{p['product_id']}: ~{p['forecast_units_total']:.0f} units "
        f"(range {p['p10_units_total']:.0f}-{p['p90_units_total']:.0f}), Rs{p['forecast_revenue']:.0f}"
        for p in products
    ]
    return {
        "type": "demand",
        "headline": headline,
        "details": details,
        "recommended_actions": ["Check material stock against forecast and re-order short items"],
    }
