"""
Delay Risk - flag orders that will likely be late, with the root cause and a fix.

Two independent checks per week:
  * Material feasibility: explode each order's BOM, net total component demand for
    the week against inventory (on-hand + on-order arriving in time). A component
    that is short puts every order using it at risk.
  * Capacity/time risk: reuse the prioritisation critical ratio (< 1 = not enough
    production time before the due date).
"""
from collections import defaultdict
from datetime import date, timedelta

from logging_config import get_logger
from data_loader import load
from services.prioritize import prioritize_week
from models import ComponentShortage, DelayRiskOrder, DelayRiskResult

log = get_logger("risk")
ACTIVE = {"Open", "Released"}


def delay_risk_week(week_start: date) -> DelayRiskResult:
    d = load()
    items, bom, comps, inv = d["items"], d["bom"], d["components"], d["inventory"]
    end = week_start + timedelta(days=7)
    orders = [o for o in d["orders"]
              if week_start <= o["due_date"] < end and o["status"] in ACTIVE]
    log.info("RISK  week %s | orders %d", week_start, len(orders))

    # aggregate component demand for the week
    required: dict = defaultdict(int)
    order_components: dict = defaultdict(list)
    for o in orders:
        for b in bom.get(o["item_id"], []):
            req = int(round(b["qty_per"] * o["quantity"]))
            required[b["component_id"]] += req
            order_components[o["order_id"]].append(b["component_id"])

    # net each component against inventory
    shortages = []
    short_ids = set()
    for cid, req in required.items():
        iv = inv.get(cid, {})
        on_hand = iv.get("on_hand", 0)
        on_order = iv.get("on_order", 0)
        rcpt = iv.get("next_receipt_date")
        arriving = on_order if (rcpt and rcpt <= end) else 0
        available = on_hand + arriving
        shortfall = max(0, req - available)
        if shortfall > 0:
            short_ids.add(cid)
            c = comps.get(cid, {})
            lt = c.get("lead_time_days", 0)
            if rcpt and rcpt > end and on_order:
                note = f"{on_order} on order but arrives {rcpt.isoformat()} (after this week)"
            else:
                note = f"only {available} available, {lt}-day lead time to replenish"
            shortages.append(ComponentShortage(
                component_id=cid, component_name=c.get("name", cid), required=req,
                available=available, shortfall=shortfall, lead_time_days=lt, note=note))
    shortages.sort(key=lambda s: -s.shortfall)

    # capacity/time risk from prioritisation
    pr = prioritize_week(week_start)
    time_risk = {o.order_id: o.at_risk for o in pr.orders}
    cr = {o.order_id: o.critical_ratio for o in pr.orders}

    risk_orders = []
    mat_count = cap_count = at_count = 0
    for o in orders:
        oid = o["order_id"]
        causes = []
        short_for_order = [cid for cid in order_components[oid] if cid in short_ids]
        material = bool(short_for_order)
        if material:
            names = [comps.get(c, {}).get("name", c) for c in short_for_order[:2]]
            causes.append("missing material: " + ", ".join(names))
            mat_count += 1
        tr = time_risk.get(oid, False)
        if tr:
            causes.append(f"tight capacity (critical ratio {cr.get(oid)})")
            cap_count += 1
        at = material or tr
        at_count += 1 if at else 0
        if material and tr:
            fix = "Expedite the short component and free up capacity (overtime/backup)."
        elif material:
            fix = "Expedite or substitute the short component, or defer this order."
        elif tr:
            fix = "Add capacity (overtime/backup) or schedule this order earlier."
        else:
            fix = "On track."
        risk_orders.append(DelayRiskOrder(
            order_id=oid, item_name=items.get(o["item_id"], {}).get("item_name", ""),
            customer_id=o["customer_id"], due_date=o["due_date"].isoformat(),
            at_risk=at, causes=causes, fix=fix))
    risk_orders.sort(key=lambda r: (not r.at_risk, r.order_id))

    if at_count == 0:
        summary = f"All {len(orders)} orders look deliverable this week."
    else:
        summary = (f"{at_count} of {len(orders)} orders at risk "
                   f"({mat_count} material, {cap_count} capacity). "
                   f"{len(shortages)} component(s) short this week.")
    log.info("RISK  %s", summary)

    return DelayRiskResult(
        week_start=week_start.isoformat(), orders_considered=len(orders),
        at_risk_count=at_count, material_risk_count=mat_count, capacity_risk_count=cap_count,
        shortages=shortages, orders=risk_orders, summary=summary)
