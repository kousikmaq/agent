"""Chart action: render an insight chart to a PNG and return it base64-encoded (plus a plain
human insight sentence) so the frontend can display, download or email it. Supports several
chart types (bar, horizontal bar, pie, line, scatter) and picks the most insightful default
per data kind. Charts are built from live analytics/ML outputs."""
from __future__ import annotations

import base64
import os
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.config import EXPORTS_DIR

CHART_KINDS = (
    "capacity", "bottleneck", "delay_risk", "downtime", "demand", "scenarios",
    "demand_regions", "fault_types", "util_vs_risk",
)
CHART_TYPES = ("bar", "barh", "pie", "line", "scatter")
_PALETTE = ["#5B8DD6", "#3FA99B", "#D9A441", "#8C6FC0", "#CC6677", "#5FA84E",
            "#E08A5B", "#6FB1C0", "#B07FC0", "#8FB84E"]


def _hi_lo(labels, values):
    hi = max(range(len(values)), key=lambda i: values[i])
    lo = min(range(len(values)), key=lambda i: values[i])
    return labels[hi], values[hi], labels[lo], values[lo]


def _spec(kind: str) -> dict:
    """Return a chart spec: {title, chart_type, labels, values|points, ylabel, insight}."""
    if kind == "capacity":
        from app.analytics.capacity import capacity_analysis
        d = capacity_analysis()["per_machine"]
        labels = [x["machine_id"] for x in d]
        values = [round(x["utilization_pct"], 1) for x in d]
        hl, hv, ll, lv = _hi_lo(labels, values)
        return {"title": "Machine Utilisation (%)", "chart_type": "bar", "labels": labels,
                "values": values, "ylabel": "Utilisation %",
                "insight": f"{hl} is the most loaded at {hv:.0f}% while {ll} has spare capacity at {lv:.0f}%. "
                           f"Bars above 100% are over capacity and need re-planning or overtime."}
    if kind == "bottleneck":
        from app.analytics.bottleneck import detect_bottlenecks
        d = detect_bottlenecks()["all_machines"]
        labels = [x["machine_id"] for x in d]
        values = [round(x["bottleneck_score"], 1) for x in d]
        top = d[0]
        return {"title": "Bottleneck Score by Machine", "chart_type": "bar", "labels": labels,
                "values": values, "ylabel": "Score",
                "insight": f"{top['machine_id']} is the biggest bottleneck (score {top['bottleneck_score']:.0f}, "
                           f"{top['reason']}). A higher bar means more strain from load, failure risk or backlog."}
    if kind == "delay_risk":
        from app.ml import registry
        d = registry.predict_delay_for_pending(top_n=8)["at_risk"]
        labels = [f"{x['order_id']}/{x['operation_id']}" for x in d]
        values = [x["delay_risk_pct"] for x in d]
        return {"title": "Top Delay-Risk Operations", "chart_type": "barh", "labels": labels,
                "values": values, "ylabel": "Delay risk %",
                "insight": f"These {len(d)} operations carry the highest chance of running late. "
                           f"Longer bars = higher risk; address the top ones first to protect deliveries."}
    if kind == "downtime":
        from app.ml import registry
        d = registry.predict_downtime_latest()["machines"]
        labels = [x["machine_id"] for x in d]
        values = [x["downtime_risk_pct"] for x in d]
        top = d[0]
        return {"title": "Machine Downtime Risk (%)", "chart_type": "bar", "labels": labels,
                "values": values, "ylabel": "Downtime risk %",
                "insight": f"{top['machine_id']} shows the highest breakdown risk ({top['downtime_risk_pct']:.0f}%). "
                           f"Machines with tall bars should be inspected before they fail."}
    if kind == "demand":
        from app.ml import registry
        d = registry.forecast_demand(horizon_days=7)["products"][:8]
        labels = [x["product_id"] for x in d]
        values = [x["forecast_units_total"] for x in d]
        hl, hv, _, _ = _hi_lo(labels, values)
        return {"title": "7-Day Demand Forecast (units)", "chart_type": "bar", "labels": labels,
                "values": values, "ylabel": "Units",
                "insight": f"{hl} has the highest forecast demand (~{hv:.0f} units next week). "
                           f"Plan production and stock around the tallest bars."}
    if kind == "scenarios":
        from app.optimization.scheduler import compare_scenarios
        sc = compare_scenarios()["scenarios"]
        labels = list(sc.keys())
        values = [v.get("total_tardiness_hours", 0) for v in sc.values()]
        best = labels[min(range(len(values)), key=lambda i: values[i])]
        return {"title": "Scenario Tardiness (hours)", "chart_type": "bar", "labels": labels,
                "values": values, "ylabel": "Tardiness hours",
                "insight": f"'{best}' gives the lowest late-delivery hours. Shorter bars protect due dates; "
                           f"the cost scenario usually trades higher tardiness for lower spend."}
    if kind == "demand_regions":
        from app.ml import registry
        shares = registry.demand_region_split()["region_share_pct"]
        labels = list(shares.keys())
        values = list(shares.values())
        hl, hv, _, _ = _hi_lo(labels, values)
        return {"title": "Demand Share by Region", "chart_type": "pie", "labels": labels,
                "values": values, "ylabel": "",
                "insight": f"{hl} accounts for the largest share of demand ({hv:.0f}%). "
                           f"Use this to decide where to stock and ship first."}
    if kind == "fault_types":
        from app import data_access as da
        s = da.machine_sensor()
        counts = s[s["downtime_flag"] == 1]["failure_type"].value_counts()
        labels = list(counts.index)
        values = [int(v) for v in counts.values]
        top = labels[0] if labels else "n/a"
        return {"title": "Downtime Fault-Type Breakdown", "chart_type": "pie", "labels": labels,
                "values": values, "ylabel": "",
                "insight": f"'{top}' is the most common fault behind downtime. "
                           f"Target maintenance at the biggest slices to cut breakdowns."}
    if kind == "util_vs_risk":
        from app.analytics.capacity import capacity_analysis
        from app.ml import registry
        cap = capacity_analysis()["per_machine"]
        probs = registry.downtime_prob_by_machine()
        points = [{"label": m["machine_id"], "x": round(m["utilization_pct"], 1),
                   "y": round(probs.get(m["machine_id"], 0.0) * 100.0, 1)} for m in cap]
        return {"title": "Utilisation vs Failure Risk", "chart_type": "scatter", "points": points,
                "xlabel": "Utilisation %", "ylabel": "Failure risk %",
                "insight": "Machines toward the top-right are both heavily loaded and likely to fail - "
                           "the riskiest combination. Prioritise those for maintenance and load-balancing."}
    raise ValueError(f"unknown chart kind '{kind}'")


def _render(spec: dict, chart_type: str, fname: str) -> str:
    fig, ax = plt.subplots(figsize=(8, 4.6))
    fig.patch.set_facecolor("#FFFFFF")

    if chart_type == "scatter":
        pts = spec["points"]
        xs = [p["x"] for p in pts]
        ys = [p["y"] for p in pts]
        ax.scatter(xs, ys, s=140, c=_PALETTE[: len(pts)], edgecolors="#33404F", zorder=3)
        for p in pts:
            ax.annotate(p["label"], (p["x"], p["y"]), textcoords="offset points",
                        xytext=(6, 6), fontsize=9, color="#1E2733")
        ax.set_xlabel(spec.get("xlabel", ""), fontsize=9, color="#5A6675")
        ax.set_ylabel(spec.get("ylabel", ""), fontsize=9, color="#5A6675")
        ax.grid(color="#E7EAEF")
        ax.spines[["top", "right"]].set_visible(False)
    else:
        labels = spec["labels"]
        values = spec["values"]
        colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(labels))]
        if chart_type == "pie":
            ax.pie(values, labels=labels, autopct="%1.0f%%", colors=colors,
                   textprops={"fontsize": 9, "color": "#1E2733"},
                   wedgeprops={"edgecolor": "#FFFFFF", "linewidth": 1.5})
            ax.axis("equal")
        elif chart_type == "barh":
            ax.barh(range(len(labels)), values, color=colors)
            ax.set_yticks(range(len(labels)))
            ax.set_yticklabels(labels, fontsize=8)
            ax.invert_yaxis()
            ax.set_xlabel(spec.get("ylabel", ""), fontsize=9, color="#5A6675")
            ax.grid(axis="x", color="#E7EAEF")
            ax.spines[["top", "right"]].set_visible(False)
        elif chart_type == "line":
            ax.plot(range(len(labels)), values, marker="o", color=_PALETTE[0], linewidth=2)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
            ax.set_ylabel(spec.get("ylabel", ""), fontsize=9, color="#5A6675")
            ax.grid(color="#E7EAEF")
            ax.spines[["top", "right"]].set_visible(False)
        else:  # bar
            ax.bar(range(len(labels)), values, color=colors)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
            ax.set_ylabel(spec.get("ylabel", ""), fontsize=9, color="#5A6675")
            ax.grid(axis="y", color="#E7EAEF")
            ax.spines[["top", "right"]].set_visible(False)

    ax.set_title(spec["title"], fontsize=13, color="#1E2733", weight="bold")
    fig.tight_layout()
    path = os.path.join(EXPORTS_DIR, fname)
    fig.savefig(path, dpi=140, facecolor="#FFFFFF")
    plt.close(fig)
    return path


def generate_chart(kind: str, chart_type: str | None = None) -> dict:
    if kind not in CHART_KINDS:
        return {"status": "error", "error": f"kind must be one of {CHART_KINDS}"}
    if chart_type is not None and chart_type not in CHART_TYPES:
        return {"status": "error", "error": f"chart_type must be one of {CHART_TYPES}"}
    try:
        spec = _spec(kind)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"could not build chart: {type(exc).__name__}"}

    ctype = chart_type or spec["chart_type"]
    if ctype == "scatter" and "points" not in spec:
        ctype = spec["chart_type"]
    if ctype != "scatter" and not spec.get("labels"):
        return {"status": "error", "error": "no data available for this chart"}

    fname = f"chart_{kind}_{ctype}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    path = _render(spec, ctype, fname)
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return {"status": "ok", "kind": kind, "chart_type": ctype, "title": spec["title"],
            "filename": fname, "path": path, "insight": spec.get("insight", ""),
            "image_base64": b64}

