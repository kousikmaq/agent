"""Export action: write a plan / list of rows to a CSV in the controlled exports directory.
Filenames are sanitised (no path traversal)."""
from __future__ import annotations

import os
import re
from datetime import datetime

import pandas as pd

from app.config import EXPORTS_DIR

_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_name(name: str) -> str:
    base = _SAFE.sub("_", (name or "export").strip())[:60] or "export"
    return f"{base}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"


def export_rows(rows: list[dict], name: str = "export") -> dict:
    if not rows:
        return {"status": "error", "error": "nothing to export"}
    fname = _safe_name(name)
    path = os.path.join(EXPORTS_DIR, fname)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")
    return {"status": "ok", "filename": fname, "path": path, "rows": len(rows)}


def export_schedule(scenario: str = "min_risk", max_orders: int = 12) -> dict:
    """Optimise then export the production plan for a scenario."""
    from app.optimization.scheduler import optimize_schedule

    plan = optimize_schedule(scenario=scenario, max_orders=max_orders)
    assignments = plan.get("assignments", [])
    if not assignments:
        return {"status": "error", "error": "no feasible schedule to export"}
    result = export_rows(assignments, name=f"production_plan_{scenario}")
    result["scenario"] = scenario
    result["kpis"] = plan.get("kpis", {})
    return result
