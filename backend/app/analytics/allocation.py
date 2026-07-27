"""Resource (workforce) allocation: skill coverage of pending work + concrete recommendations."""
from __future__ import annotations

from app import data_access as da
from app.analytics._util import pending_jobs, round_floats

SHIFT_HOURS = 8.0


def allocate_resources(top_operations: int = 8) -> dict:
    """Assess whether available, qualified workers can cover pending work per skill,
    and recommend cheapest qualified workers for the most urgent operations."""
    ops = da.operations().set_index("operation_id")
    workers = da.workers()
    avail = da.worker_shift_availability()
    pend = pending_jobs()

    # available workers (>=1 available slot in the planning week), by primary skill
    avail_workers = set(avail[avail["available"] == 1]["worker_id"].unique())
    active = workers[workers["worker_id"].isin(avail_workers)]

    # ---- skill coverage (available worker-hours vs required worker-hours) ----
    op_skill = ops["required_skill"].to_dict()
    op_minw = ops["min_workers"].to_dict()
    pend = pend.copy()
    pend["skill"] = pend["operation_id"].map(op_skill)
    pend["min_workers"] = pend["operation_id"].map(op_minw).astype(float)
    pend["required_worker_hours"] = pend["processing_hours"] * pend["min_workers"]
    required_by_skill = pend.groupby("skill")["required_worker_hours"].sum().to_dict()

    # available worker-hours this planning week, attributed to each worker's primary skill
    avail_hours = avail[avail["available"] == 1].merge(
        workers[["worker_id", "primary_skill"]], on="worker_id", how="left"
    )
    supply_hours_by_skill = avail_hours.groupby("primary_skill")["available_hours"].sum().to_dict()
    supply_headcount = active.groupby("primary_skill")["worker_id"].count().to_dict()

    coverage = []
    gaps = []
    for skill, req_hours in required_by_skill.items():
        supply_hours = float(supply_hours_by_skill.get(skill, 0.0))
        ratio = (supply_hours / req_hours) if req_hours else 1.0
        entry = {
            "skill": skill,
            "required_worker_hours": float(req_hours),
            "available_worker_hours": supply_hours,
            "available_workers": int(supply_headcount.get(skill, 0)),
            "coverage_ratio": ratio,
            "status": "SHORTFALL" if ratio < 1.0 else "OK",
        }
        coverage.append(entry)
        if ratio < 1.0:
            gaps.append(skill)

    # ---- concrete recommendations for the most urgent pending operations ----
    urgent = pend.sort_values(["due_date", "priority"]).head(top_operations)
    recommendations = []
    for _, job in urgent.iterrows():
        skill = job["skill"]
        machine = job["machine_id"]
        candidates = active[
            (active["primary_skill"] == skill)
            & (active["machine_qualifications"].str.contains(machine, na=False))
        ].sort_values("hourly_cost_inr")
        if candidates.empty:
            candidates = active[active["primary_skill"] == skill].sort_values("hourly_cost_inr")
        pick = candidates.iloc[0] if not candidates.empty else None
        recommendations.append({
            "order_id": job["order_id"],
            "operation_id": job["operation_id"],
            "machine_id": machine,
            "required_skill": skill,
            "recommended_worker": (pick["worker_id"] if pick is not None else None),
            "worker_hourly_cost_inr": (float(pick["hourly_cost_inr"]) if pick is not None else None),
            "note": "no qualified available worker" if pick is None else "cheapest qualified & available",
        })

    return round_floats({
        "skill_coverage": coverage,
        "skill_gaps": gaps,
        "recommendations": recommendations,
    })
