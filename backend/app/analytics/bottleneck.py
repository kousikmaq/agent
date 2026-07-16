"""Bottleneck detection.

Composite 0-1 score from three unit-normalised signals (weights are tunable):

    score = W_LOAD * load_norm  +  W_FAIL * failure_prob  +  W_QUEUE * backlog_norm

    load_norm    = min(utilisation%, UTIL_CAP) / UTIL_CAP     (how saturated)
    failure_prob = predicted downtime probability 0-1         (how likely to break)
    backlog_norm = min(queue, queue_max) / queue_max          (how much waiting work)

Also outputs the dominant reason, a severity band, and the predicted queue wait (hours).
"""
from __future__ import annotations

from app import data_access as da
from app.analytics._util import pending_jobs, round_floats
from app.analytics.capacity import capacity_analysis

# tunable knobs
W_LOAD, W_FAIL, W_QUEUE = 0.55, 0.30, 0.15
UTIL_CAP = 150.0
SEVERITY_HIGH, SEVERITY_MED = 0.66, 0.40


def detect_bottlenecks(horizon_days: int = 7, top_n: int = 3) -> dict:
    cap = capacity_analysis(horizon_days)
    util_by = {r["machine_id"]: r["utilization_pct"] for r in cap["per_machine"]}
    # predicted processing hours ahead per machine = queue wait time
    wait_by = {r["machine_id"]: r["required_hours"] for r in cap["per_machine"]}

    pend = pending_jobs()
    queue = pend.groupby("machine_id")["job_id"].count().to_dict()
    queue_max = max([1] + list(queue.values()))

    try:
        from app.ml import registry
        fail_probs = registry.downtime_prob_by_machine()
    except Exception:  # noqa: BLE001
        fail_probs = {}

    machines = da.machines()
    scored = []
    for _, m in machines.iterrows():
        mid = m["machine_id"]
        util = util_by.get(mid, 0.0)
        fail = float(min(max(fail_probs.get(mid, 1.0 - float(m["reliability_index"])), 0.0), 1.0))
        q = int(queue.get(mid, 0))

        load_norm = min(util, UTIL_CAP) / UTIL_CAP
        backlog_norm = q / queue_max
        c_load = W_LOAD * load_norm
        c_fail = W_FAIL * fail
        c_queue = W_QUEUE * backlog_norm
        score01 = c_load + c_fail + c_queue

        reason = max(
            [("load-bound", c_load), ("failure-bound", c_fail), ("backlog-bound", c_queue)],
            key=lambda t: t[1],
        )[0]
        severity = ("High" if score01 >= SEVERITY_HIGH
                    else "Medium" if score01 >= SEVERITY_MED else "Low")

        scored.append({
            "machine_id": mid,
            "machine_name": m["machine_name"],
            "utilization_pct": util,
            "failure_probability_pct": fail * 100.0,
            "pending_jobs": q,
            "predicted_queue_wait_hours": wait_by.get(mid, 0.0),
            "bottleneck_score": score01 * 100.0,
            "reason": reason,
            "severity": severity,
        })

    scored.sort(key=lambda r: r["bottleneck_score"], reverse=True)
    top = scored[:top_n]
    return round_floats({
        "horizon_days": horizon_days,
        "weights": {"load": W_LOAD, "failure": W_FAIL, "backlog": W_QUEUE},
        "primary_bottleneck": top[0]["machine_id"] if top else None,
        "primary_reason": top[0]["reason"] if top else None,
        "bottlenecks": top,
        "all_machines": scored,
    })
