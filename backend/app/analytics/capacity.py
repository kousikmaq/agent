"""Capacity analysis.

Utilisation = sum of PREDICTED operation durations (from the duration/cycle-time model)
divided by machine availability, where availability is de-rated by the machine's predicted
downtime probability. Falls back to recorded processing times if the models are not trained.

Extra outputs: P90 (worst-case) utilisation, downtime-adjusted vs raw available hours,
expected shortfall hours, and suggested overtime.
"""
from __future__ import annotations

from app import data_access as da
from app.analytics._util import pending_jobs, round_floats

HOURS_PER_DAY = 24.0            # up to 3 shifts x 8h
DOWNTIME_DERATE_CAP = 0.5      # never de-rate availability by more than 50%
CONSTRAINED_AT = 0.85


def _with_predicted_durations(pend):
    """Attach pred_hours / pred_hours_p90 columns (predicted, else recorded fallback)."""
    pend = pend.copy()
    try:
        from app.ml import registry
        pend["pred_hours"] = registry.predict_duration(pend)
        pend["pred_hours_p90"] = registry.predict_duration_p90(pend)
        method = "predicted-duration"
    except Exception:  # noqa: BLE001 - model missing -> graceful fallback
        pend["pred_hours"] = pend["processing_hours"]
        pend["pred_hours_p90"] = pend["processing_hours"] * 1.25
        method = "recorded-duration (duration model not trained)"
    return pend, method


def _downtime_fractions() -> dict:
    """Predicted downtime fraction (0-1) per machine, capped."""
    try:
        from app.ml import registry
        return registry.downtime_prob_by_machine()
    except Exception:  # noqa: BLE001
        return {}


def capacity_analysis(horizon_days: int = 7) -> dict:
    machines = da.machines()
    pend, method = _with_predicted_durations(pending_jobs())
    req = pend.groupby("machine_id")["pred_hours"].sum().to_dict()
    req_p90 = pend.groupby("machine_id")["pred_hours_p90"].sum().to_dict()
    down_probs = _downtime_fractions()

    per_machine = []
    total_req = total_avail = total_shortfall = 0.0
    for _, m in machines.iterrows():
        mid = m["machine_id"]
        reliability = float(m["reliability_index"])
        down_frac = min(max(down_probs.get(mid, 1.0 - reliability), 0.0), DOWNTIME_DERATE_CAP)

        raw_avail = horizon_days * HOURS_PER_DAY
        avail = raw_avail * (1.0 - down_frac)
        required = float(req.get(mid, 0.0))
        required_p90 = float(req_p90.get(mid, 0.0))
        util = (required / avail) if avail else 0.0
        util_p90 = (required_p90 / avail) if avail else 0.0
        shortfall = max(0.0, required - avail)

        total_req += required
        total_avail += avail
        total_shortfall += shortfall
        per_machine.append({
            "machine_id": mid,
            "machine_name": m["machine_name"],
            "required_hours": required,
            "raw_available_hours": raw_avail,
            "downtime_derate_pct": down_frac * 100.0,
            "available_hours": avail,
            "utilization_pct": util * 100.0,
            "p90_utilization_pct": util_p90 * 100.0,
            "expected_shortfall_hours": shortfall,
            "suggested_overtime_hours": shortfall,
            "status": "OVER_CAPACITY" if util > 1.0 else ("CONSTRAINED" if util > CONSTRAINED_AT else "OK"),
        })

    per_machine.sort(key=lambda r: r["utilization_pct"], reverse=True)
    overall = (total_req / total_avail) if total_avail else 0.0
    constrained = [r["machine_id"] for r in per_machine if r["status"] != "OK"]

    return round_floats({
        "method": method,
        "horizon_days": horizon_days,
        "overall_utilization_pct": overall * 100.0,
        "total_required_hours": total_req,
        "total_available_hours": total_avail,
        "total_expected_shortfall_hours": total_shortfall,
        "constrained_machines": constrained,
        "verdict": (
            "Capacity shortfall - predicted load exceeds availability on one or more machines"
            if constrained else
            "Capacity sufficient for the predicted load in this horizon"
        ),
        "per_machine": per_machine,
    })
