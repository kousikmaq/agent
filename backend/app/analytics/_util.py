"""Shared helpers for analytics: the set of "pending" work to plan."""
from __future__ import annotations

import pandas as pd

from app import data_access as da

PENDING_STATUSES = ("Open", "Scheduled")


def pending_jobs() -> pd.DataFrame:
    """Job-operations belonging to orders that still need to run, enriched with order info."""
    jobs = da.job_operations()
    orders = da.orders()[["order_id", "status", "due_date", "priority", "customer_region"]]
    merged = jobs.merge(orders, on="order_id", how="left")
    return merged[merged["status"].isin(PENDING_STATUSES)].copy()


def planning_now() -> pd.Timestamp:
    """Reference 'now' for the planning horizon (latest order release in the dataset)."""
    return da.orders()["release_date"].max()


def round_floats(obj, ndigits: int = 2):
    """Recursively round floats for clean JSON output."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, ndigits) for v in obj]
    return obj
