"""Material re-order action. Validates the material and quantity, computes cost/lead time
from the material master, and records a purchase order in the local outbox (simulated —
no real external procurement call)."""
from __future__ import annotations

import json
import os
from datetime import datetime

from app import data_access as da
from app.config import OUTBOX_DIR

_PO_LOG = os.path.join(OUTBOX_DIR, "purchase_orders.jsonl")
MAX_QTY = 10_000_000


def place_reorder(material_id: str, quantity: int, reason: str = "") -> dict:
    """Record a purchase order for a material. Returns a PO dict or an error dict."""
    materials = da.materials()
    row = materials[materials["material_id"] == material_id]
    if row.empty:
        return {"status": "error", "error": f"unknown material_id '{material_id}'"}
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        return {"status": "error", "error": "quantity must be an integer"}
    if qty <= 0 or qty > MAX_QTY:
        return {"status": "error", "error": "quantity out of allowed range"}

    m = row.iloc[0]
    unit_cost = float(m["unit_cost"])
    po = {
        "po_id": f"PO{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "material_id": material_id,
        "material_name": m["material_name"],
        "supplier_id": m["supplier_id"],
        "quantity": qty,
        "unit_cost_inr": unit_cost,
        "estimated_cost_inr": round(unit_cost * qty, 2),
        "lead_time_days": int(m["supplier_lead_time_days"]),
        "reason": reason[:500],
        "po_status": "PLACED_SIMULATED",
    }
    with open(_PO_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(po) + "\n")

    # auto-send an order confirmation email to the default recipient in .env
    from app.actions.email_action import send_alert_email
    from app.config import settings
    subject = f"Purchase Order {po['po_id']} - {po['material_name']} x{qty:,}"
    body = (
        "A purchase order has been placed by the Production Planning Agent.\n\n"
        f"PO number      : {po['po_id']}\n"
        f"Material        : {po['material_id']} - {po['material_name']}\n"
        f"Quantity        : {qty:,} {m['unit_of_measure']}\n"
        f"Unit cost       : Rs {unit_cost:,.2f}\n"
        f"Estimated cost  : Rs {po['estimated_cost_inr']:,.2f}\n"
        f"Supplier        : {po['supplier_id']}\n"
        f"Lead time       : {po['lead_time_days']} days\n"
        f"Reason          : {reason or 'stock below reorder point'}\n"
        f"Placed at       : {po['timestamp']}\n\n"
        "This is an automated confirmation. No action is required."
    )
    email = send_alert_email(subject, body, to=settings.alert_email_to)
    return {"status": "placed", **po, "email_status": email.get("status"),
            "email_to": email.get("to")}


def reorder_recommendations(forecast_horizon_days: int = 7) -> dict:
    """Recommend materials to re-order: current stock below reorder point, sized to cover
    forecast demand. Pairs with place_reorder for a one-click action."""
    from app.ml import registry

    materials = da.materials()
    products = da.products()[["product_id", "base_material_id"]]
    try:
        fc = registry.forecast_demand(horizon_days=forecast_horizon_days).get("products", [])
    except Exception:
        fc = []
    demand_by_material: dict[str, float] = {}
    fc_map = {f["product_id"]: f["forecast_units_total"] for f in fc}
    for _, p in products.iterrows():
        demand_by_material.setdefault(p["base_material_id"], 0.0)
        demand_by_material[p["base_material_id"]] += fc_map.get(p["product_id"], 0.0)

    recs = []
    for _, m in materials.iterrows():
        stock = float(m["current_stock"])
        reorder_pt = float(m["reorder_point"])
        forecast = demand_by_material.get(m["material_id"], 0.0)
        if stock <= reorder_pt or stock < forecast:
            suggested = int(max(reorder_pt * 2 - stock, forecast - stock, 0)) or int(reorder_pt)
            recs.append({
                "material_id": m["material_id"],
                "material_name": m["material_name"],
                "current_stock": int(stock),
                "reorder_point": int(reorder_pt),
                "forecast_demand": round(forecast, 1),
                "suggested_quantity": suggested,
                "estimated_cost_inr": round(float(m["unit_cost"]) * suggested, 2),
            })
    return {"count": len(recs), "recommendations": recs}
