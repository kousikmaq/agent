"""
Demand vs Capacity - the horizon-level question: "can we commit to the whole
order book?"

Sums the total work each machine (and department) must do across the entire
planning horizon and compares it to the total available hours. Reports an overall
verdict, the gap, and - importantly - notes that being feasible in total does not
mean every week is feasible (weekly peaks still need smoothing).
"""
from collections import defaultdict

from logging_config import get_logger
from data_loader import load
from services.capacity import overview
from models import ResourceDemand, DepartmentDemand, DemandVsCapacity

log = get_logger("demand")
ACTIVE = {"Open", "Released"}


def demand_vs_capacity() -> DemandVsCapacity:
    d = load()
    wcs, routings, weeks = d["work_centers"], d["routings"], d["weeks"]
    n_weeks = len(weeks)
    orders = [o for o in d["orders"] if o["status"] in ACTIVE]
    log.info("DEMAND  horizon %d weeks | active orders %d", n_weeks, len(orders))

    req_min: dict = defaultdict(float)
    for o in orders:
        for op in routings.get(o["item_id"], []):
            req_min[op["work_center"]] += op["setup_min"] + op["run_min_per_unit"] * o["quantity"]

    resources = []
    dept_req: dict = defaultdict(float)
    dept_av: dict = defaultdict(float)
    for wc_id, wc in wcs.items():
        rh = round(req_min.get(wc_id, 0.0) / 60.0, 1)
        av = round(wc["weekly_capacity_hours"] * n_weeks, 1)
        util = round(rh / av * 100, 1) if av else 0.0
        gap = round(max(0.0, rh - av), 1)
        resources.append(ResourceDemand(
            work_center=wc_id, name=wc["name"], department=wc["department"],
            required_hours=rh, available_hours=av, utilization_pct=util,
            gap_hours=gap, feasible=rh <= av))
        dept_req[wc["department"]] += rh
        dept_av[wc["department"]] += av
    resources.sort(key=lambda r: -r.utilization_pct)

    departments = []
    for dept in dept_req:
        rh, av = round(dept_req[dept], 1), round(dept_av[dept], 1)
        util = round(rh / av * 100, 1) if av else 0.0
        departments.append(DepartmentDemand(
            department=dept, required_hours=rh, available_hours=av,
            utilization_pct=util, gap_hours=round(max(0.0, rh - av), 1), feasible=rh <= av))
    departments.sort(key=lambda x: -x.utilization_pct)

    tot_req = round(sum(r.required_hours for r in resources), 1)
    tot_av = round(sum(r.available_hours for r in resources), 1)
    tot_util = round(tot_req / tot_av * 100, 1) if tot_av else 0.0
    gap = round(max(0.0, tot_req - tot_av), 1)
    feasible = tot_req <= tot_av

    overloaded_weeks = overview().overloaded_weeks
    short = [r for r in resources if not r.feasible]

    if short:
        verdict = (f"Cannot fully commit: {len(short)} resource(s) are short over the "
                   f"{n_weeks}-week horizon (total gap {gap:.0f}h). Add capacity or reduce load.")
    elif overloaded_weeks:
        verdict = (f"Committable overall (total load {tot_util:.0f}%), but {overloaded_weeks} "
                   f"week(s) are overloaded - smooth demand across weeks or add short-term capacity.")
    else:
        verdict = f"Fully committable: total load is {tot_util:.0f}% with no overloaded weeks."

    fixes = []
    for r in short:
        fixes.append(f"{r.work_center} ({r.name}): short {r.gap_hours:.0f}h over the horizon - "
                     f"add overtime/a shift, outsource, or defer some orders.")
    if not short and overloaded_weeks:
        fixes.append(f"Rebalance the {overloaded_weeks} peak week(s) into lighter weeks "
                     f"(see the capacity heatmap).")
    if not fixes:
        fixes.append("No action needed - the order book fits comfortably.")

    log.info("DEMAND  %s", verdict)
    return DemandVsCapacity(
        horizon_weeks=n_weeks, overall_required_hours=tot_req, overall_available_hours=tot_av,
        overall_utilization_pct=tot_util, overall_gap_hours=gap, overall_feasible=feasible,
        overloaded_weeks=overloaded_weeks, verdict=verdict, fixes=fixes,
        departments=departments, resources=resources)
