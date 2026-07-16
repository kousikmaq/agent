"""Chart action: render an insight chart (light theme) to a PNG and return it base64-encoded
so the frontend can display it inline. Charts are built from live analytics/ML outputs."""
from __future__ import annotations

import base64
import os
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.config import EXPORTS_DIR

CHART_KINDS = ("capacity", "bottleneck", "delay_risk", "downtime", "demand", "scenarios")
_PALETTE = ["#5B8DD6", "#3FA99B", "#D9A441", "#8C6FC0", "#CC6677", "#5FA84E"]


def _series_for(kind: str) -> tuple[str, list[str], list[float], str]:
    """Return (title, labels, values, ylabel) for a chart kind."""
    if kind == "capacity":
        from app.analytics.capacity import capacity_analysis
        data = capacity_analysis()["per_machine"]
        return ("Machine Utilisation (%)", [d["machine_id"] for d in data],
                [d["utilization_pct"] for d in data], "Utilisation %")
    if kind == "bottleneck":
        from app.analytics.bottleneck import detect_bottlenecks
        data = detect_bottlenecks()["all_machines"]
        return ("Bottleneck Score by Machine", [d["machine_id"] for d in data],
                [d["bottleneck_score"] for d in data], "Score")
    if kind == "delay_risk":
        from app.ml import registry
        data = registry.predict_delay_for_pending(top_n=8)["at_risk"]
        return ("Top Delay-Risk Operations", [f"{d['order_id']}/{d['operation_id']}" for d in data],
                [d["delay_risk_pct"] for d in data], "Delay risk %")
    if kind == "downtime":
        from app.ml import registry
        data = registry.predict_downtime_latest()["machines"]
        return ("Machine Downtime Risk (%)", [d["machine_id"] for d in data],
                [d["downtime_risk_pct"] for d in data], "Downtime risk %")
    if kind == "demand":
        from app.ml import registry
        data = registry.forecast_demand(horizon_days=7)["products"][:8]
        return ("7-Day Demand Forecast (units)", [d["product_id"] for d in data],
                [d["forecast_units_total"] for d in data], "Units")
    if kind == "scenarios":
        from app.optimization.scheduler import compare_scenarios
        sc = compare_scenarios()["scenarios"]
        return ("Scenario Tardiness (hours)", list(sc.keys()),
                [v.get("total_tardiness_hours", 0) for v in sc.values()], "Tardiness hours")
    raise ValueError(f"unknown chart kind '{kind}'")


def generate_chart(kind: str) -> dict:
    if kind not in CHART_KINDS:
        return {"status": "error", "error": f"kind must be one of {CHART_KINDS}"}
    title, labels, values, ylabel = _series_for(kind)
    if not labels:
        return {"status": "error", "error": "no data available for this chart"}

    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor("#FFFFFF")
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(labels))]
    ax.bar(range(len(labels)), values, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.set_title(title, fontsize=12, color="#1E2733", weight="bold")
    ax.set_ylabel(ylabel, fontsize=9, color="#5A6675")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#E7EAEF")
    fig.tight_layout()

    fname = f"chart_{kind}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    path = os.path.join(EXPORTS_DIR, fname)
    fig.savefig(path, dpi=140, facecolor="#FFFFFF")
    plt.close(fig)

    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return {"status": "ok", "kind": kind, "filename": fname, "path": path,
            "image_base64": b64}
