"""Capacity analysis: available machine-hours vs required load over a planning horizon."""
from __future__ import annotations

from app import data_access as da
from app.analytics._util import pending_jobs, round_floats

HOURS_PER_DAY = 24.0  # up to 3 shifts x 8h


def capacity_analysis(horizon_days: int = 7) -> dict:
    """Compare required processing hours to available machine capacity per machine.

    Available hours are de-rated by each machine's reliability_index (a proxy for
    planned downtime). A machine over ~85% utilisation is flagged as constrained.
    """
    machines = da.machines()
    pend = pending_jobs()
    required = pend.groupby("machine_id")["processing_hours"].sum().to_dict()

    per_machine = []
    total_required = total_available = 0.0
    for _, m in machines.iterrows():
        mid = m["machine_id"]
        avail = horizon_days * HOURS_PER_DAY * float(m["reliability_index"])
        req = float(required.get(mid, 0.0))
        util = (req / avail) if avail else 0.0
        total_required += req
        total_available += avail
        per_machine.append({
            "machine_id": mid,
            "machine_name": m["machine_name"],
            "required_hours": req,
            "available_hours": avail,
            "utilization_pct": util * 100.0,
            "status": "OVER_CAPACITY" if util > 1.0 else ("CONSTRAINED" if util > 0.85 else "OK"),
        })

    per_machine.sort(key=lambda r: r["utilization_pct"], reverse=True)
    overall_util = (total_required / total_available) if total_available else 0.0
    constrained = [r["machine_id"] for r in per_machine if r["status"] != "OK"]

    return round_floats({
        "horizon_days": horizon_days,
        "overall_utilization_pct": overall_util * 100.0,
        "total_required_hours": total_required,
        "total_available_hours": total_available,
        "constrained_machines": constrained,
        "verdict": (
            "Capacity shortfall - required load exceeds ~85% on one or more machines"
            if constrained else
            "Capacity sufficient for the pending load in this horizon"
        ),
        "per_machine": per_machine,
    })
