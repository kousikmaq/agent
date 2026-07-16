"""Bottleneck detection: rank machines by load, queue depth and historical downtime."""
from __future__ import annotations

from app import data_access as da
from app.analytics._util import pending_jobs, round_floats
from app.analytics.capacity import capacity_analysis


def detect_bottlenecks(horizon_days: int = 7, top_n: int = 3) -> dict:
    """Combine utilisation, pending-job queue depth and historical downtime into a
    single bottleneck score per machine, then return the worst offenders."""
    cap = capacity_analysis(horizon_days)
    util_by_machine = {r["machine_id"]: r["utilization_pct"] for r in cap["per_machine"]}

    pend = pending_jobs()
    queue = pend.groupby("machine_id")["job_id"].count().to_dict()

    hist = da.production_history()
    downtime = hist.groupby("machine_id")["downtime_hours"].mean().to_dict()

    machines = da.machines()
    scored = []
    for _, m in machines.iterrows():
        mid = m["machine_id"]
        util = util_by_machine.get(mid, 0.0)
        q = int(queue.get(mid, 0))
        dt = float(downtime.get(mid, 0.0))
        # normalized composite score (0-100)
        score = 0.6 * min(util, 150.0) + 0.25 * min(q, 100) + 0.15 * (dt * 20.0)
        scored.append({
            "machine_id": mid,
            "machine_name": m["machine_name"],
            "utilization_pct": util,
            "pending_jobs": q,
            "avg_downtime_hours": dt,
            "bottleneck_score": score,
        })

    scored.sort(key=lambda r: r["bottleneck_score"], reverse=True)
    top = scored[:top_n]
    return round_floats({
        "horizon_days": horizon_days,
        "primary_bottleneck": top[0]["machine_id"] if top else None,
        "bottlenecks": top,
        "all_machines": scored,
    })
