"""
Loads the CSV dataset (app/backend/data) once and caches it in memory,
then offers simple lookups the capacity engine uses.
"""
import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

from logging_config import get_logger

log = get_logger("data")
DATA_DIR = Path(__file__).parent / "data"

_CACHE: dict = {}


def _read(name: str) -> List[dict]:
    with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def load() -> dict:
    """Load and index everything once."""
    if _CACHE:
        return _CACHE

    log.info("Loading dataset from %s", DATA_DIR)
    work_centers = {r["work_center_id"]: {
        "id": r["work_center_id"], "name": r["name"], "department": r["department"],
        "hours_per_shift": float(r["hours_per_shift"]),
        "shifts_per_day": int(r["shifts_per_day"]),
        "days_per_week": int(r["days_per_week"]),
        "weekly_capacity_hours": float(r["weekly_capacity_hours"]),
    } for r in _read("work_centers.csv")}

    items = {r["item_id"]: r for r in _read("items.csv")}

    customers = {r["customer_id"]: {
        "customer_id": r["customer_id"], "name": r["customer_name"], "tier": r["tier"],
        "penalty_per_day_usd": float(r["penalty_per_day_usd"]),
    } for r in _read("customers.csv")}

    routings: Dict[str, list] = {}
    for r in _read("routings.csv"):
        routings.setdefault(r["item_id"], []).append({
            "op_seq": int(r["op_seq"]), "work_center": r["work_center_id"],
            "setup_min": float(r["setup_min"]), "run_min_per_unit": float(r["run_min_per_unit"]),
            "alt_work_center": r["alt_work_center_id"] or None,
        })

    orders = []
    for r in _read("orders.csv"):
        due = date.fromisoformat(r["due_date"])
        orders.append({
            "order_id": r["order_id"], "item_id": r["item_id"], "customer_id": r["customer_id"],
            "quantity": int(r["quantity"]), "due_date": due, "week_start": _monday(due),
            "priority": r["priority"], "status": r["status"],
        })

    components = {r["component_id"]: {
        "component_id": r["component_id"], "name": r["component_name"],
        "category": r["category"], "lead_time_days": int(r["lead_time_days"]),
    } for r in _read("components.csv")}

    bom: Dict[str, list] = {}
    for r in _read("bom.csv"):
        bom.setdefault(r["item_id"], []).append({
            "component_id": r["component_id"], "qty_per": float(r["qty_per"]),
        })

    inventory = {}
    for r in _read("inventory.csv"):
        rcpt = r["next_receipt_date"]
        inventory[r["component_id"]] = {
            "on_hand": int(r["on_hand_qty"]), "reorder_point": int(r["reorder_point"]),
            "on_order": int(r["on_order_qty"]),
            "next_receipt_date": date.fromisoformat(rcpt) if rcpt else None,
        }

    weeks = sorted({o["week_start"] for o in orders})

    _CACHE.update(work_centers=work_centers, items=items, customers=customers,
                  routings=routings, orders=orders, weeks=weeks,
                  components=components, bom=bom, inventory=inventory,
                  counts={
                      "work_centers": len(work_centers), "items": len(items),
                      "routings": sum(len(v) for v in routings.values()),
                      "orders": len(orders),
                  })
    log.info("Dataset loaded: %d orders, %d items, %d work centers, %d weeks",
             len(orders), len(items), len(work_centers), len(weeks))
    return _CACHE


def dataset_counts() -> dict:
    d = load()
    # add the tables we do not index but still want to report
    extra = {}
    for name, key in (("components.csv", "components"), ("bom.csv", "bom"),
                      ("inventory.csv", "inventory"), ("customers.csv", "customers")):
        try:
            extra[key] = len(_read(name))
        except FileNotFoundError:
            pass
    return {**d["counts"], **extra}
