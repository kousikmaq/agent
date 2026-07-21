"""
Order Prioritization - decide which orders to run first, and explain why.

Method (simple, explainable, no solver needed):
  * Earliest Due Date (EDD): sooner due = more urgent.
  * Critical Ratio (CR): production days available until due vs production days of
    work still to do. CR < 1 means there is not enough time -> at risk.
  * Business weight: customer tier (A/B/C) and any late-delivery penalty.

Each order gets a 0-100 urgency score; higher = run sooner. Every driver is shown.
"""
from datetime import date, timedelta
from functools import lru_cache

from logging_config import get_logger
from data_loader import load
from models import OrderPriority, PriorityResult

log = get_logger("priority")

ACTIVE = {"Open", "Released"}
TIER_WEIGHT = {"A": 1.0, "B": 0.5, "C": 0.2}
DAILY_HOURS = 8.0  # one shift-day of production time used for the critical ratio


def _processing_hours(item_id: str, qty: int) -> float:
    total_min = 0.0
    for op in load()["routings"].get(item_id, []):
        total_min += op["setup_min"] + op["run_min_per_unit"] * qty
    return total_min / 60.0


@lru_cache(maxsize=None)
def prioritize_week(week_start: date) -> PriorityResult:
    d = load()
    items, customers = d["items"], d["customers"]
    # Reference point = the start of the week we are sequencing.
    as_of = week_start
    end = week_start + timedelta(days=7)
    orders = [o for o in d["orders"]
              if week_start <= o["due_date"] < end and o["status"] in ACTIVE]
    log.info("PRIORITY  week %s | orders %d", week_start, len(orders))

    scored = []
    for o in orders:
        cust = customers.get(o["customer_id"], {})
        tier = cust.get("tier", "C")
        penalty = cust.get("penalty_per_day_usd", 0) > 0

        days_to_due = (o["due_date"] - as_of).days
        proc_h = round(_processing_hours(o["item_id"], o["quantity"]), 1)
        prod_days_needed = max(proc_h / DAILY_HOURS, 0.1)
        cr = round((days_to_due + 1) / prod_days_needed, 2)   # +1 so day-0 still has a value
        at_risk = cr < 1.0

        # urgency score 0-100 (higher = sooner). Blend the drivers.
        due_score = 40 * (1 / (1 + max(days_to_due, 0) / 7))      # sooner due -> higher
        cr_score = 30 * (1 / max(cr, 0.2)) if cr < 3 else 0        # tight CR -> higher
        cr_score = min(cr_score, 30)
        tier_score = 20 * TIER_WEIGHT.get(tier, 0.2)
        penalty_score = 10 if penalty else 0
        score = round(min(due_score + cr_score + tier_score + penalty_score, 100), 1)

        reasons = [f"due in {days_to_due}d"]
        if at_risk:
            reasons.append(f"tight (CR {cr})")
        if tier == "A":
            reasons.append("key customer (A)")
        if penalty:
            reasons.append("penalty if late")

        scored.append({
            "o": o, "tier": tier, "days_to_due": days_to_due, "proc_h": proc_h,
            "cr": cr, "at_risk": at_risk, "score": score, "reasons": reasons,
        })

    # sort by score desc, then earliest due, then most work
    scored.sort(key=lambda s: (-s["score"], s["days_to_due"], -s["proc_h"]))

    ranked = []
    for i, s in enumerate(scored, 1):
        o = s["o"]
        ranked.append(OrderPriority(
            rank=i, order_id=o["order_id"],
            item_name=items.get(o["item_id"], {}).get("item_name", o["item_id"]),
            customer_id=o["customer_id"], tier=s["tier"], quantity=o["quantity"],
            due_date=o["due_date"].isoformat(), days_to_due=s["days_to_due"],
            processing_hours=s["proc_h"], critical_ratio=s["cr"],
            score=s["score"], at_risk=s["at_risk"], reasons=s["reasons"],
        ))
    log.info("PRIORITY  ranked %d orders (%d at risk)", len(ranked),
             sum(1 for r in ranked if r.at_risk))
    return PriorityResult(week_start=week_start.isoformat(), as_of=as_of.isoformat(),
                          orders_considered=len(orders), orders=ranked)
