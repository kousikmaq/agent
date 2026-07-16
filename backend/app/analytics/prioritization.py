"""Order prioritization: rule-based score from due-date urgency, priority and order value."""
from __future__ import annotations

import pandas as pd

from app import data_access as da
from app.analytics._util import planning_now, round_floats

PENDING_STATUSES = ("Open", "Scheduled")


def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.5, index=s.index)
    return (s - lo) / (hi - lo)


def prioritize_orders(top_n: int = 10) -> dict:
    """Rank pending orders. Score = 0.5*urgency + 0.3*priority + 0.2*value (all 0-1)."""
    orders = da.orders()
    prods = da.products()[["product_id", "product_name", "standard_unit_price"]]
    pend = orders[orders["status"].isin(PENDING_STATUSES)].merge(prods, on="product_id", how="left")
    if pend.empty:
        return {"count": 0, "ranked_orders": []}

    now = planning_now()
    pend = pend.copy()
    pend["days_to_due"] = (pend["due_date"] - now).dt.days
    pend["order_value"] = pend["order_quantity"] * pend["standard_unit_price"]

    # urgency: fewer days-to-due -> more urgent (invert)
    urgency = 1.0 - _minmax(pend["days_to_due"])
    priority_score = 1.0 - _minmax(pend["priority"].astype(float))  # priority 1 = high
    value_score = _minmax(pend["order_value"])
    pend["priority_score"] = (0.5 * urgency + 0.3 * priority_score + 0.2 * value_score) * 100.0

    pend = pend.sort_values("priority_score", ascending=False).head(top_n)
    ranked = [
        {
            "rank": i + 1,
            "order_id": r["order_id"],
            "product": r["product_name"],
            "due_date": r["due_date"].strftime("%d-%m-%Y"),
            "days_to_due": int(r["days_to_due"]),
            "priority": int(r["priority"]),
            "order_quantity": int(r["order_quantity"]),
            "order_value": float(r["order_value"]),
            "priority_score": float(r["priority_score"]),
        }
        for i, (_, r) in enumerate(pend.iterrows())
    ]
    return round_floats({"count": len(ranked), "ranked_orders": ranked})
