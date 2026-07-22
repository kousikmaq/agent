"""Per-tab report email rendering.

Turns the persisted, deterministic results (curated ExplanationSummary + KpiSet)
into professional, self-contained HTML emails - one tailored report per UI tab
(overview, weekly, orders, scenarios, machines, ...). Content is addressed to a
named operational role so the recipient immediately understands the context.

Reuses the shared email shell/helpers from :mod:`app.notifications.templates`.
"""

from __future__ import annotations

from html import escape

from app.domain.models.analytics import KpiSet
from app.explanation.schema import ExplanationSummary
from app.notifications.templates import (
    _BORDER,
    _BG,
    _INK,
    _MUTED,
    _PRIMARY,
    _SEVERITY_COLOR,
    _chip,
    _shell,
)

# Operational roles a report can be addressed to (shown in the UI dropdown).
ROLES: tuple[str, ...] = (
    "Production Planner",
    "Manufacturing Manager",
    "Operations Manager",
    "Plant Scheduler",
)

# report_type -> (email title, one-line description of what the report is).
REPORT_META: dict[str, tuple[str, str]] = {
    "overview": (
        "Daily Operations Overview",
        "A headline snapshot of today's production plan: KPIs, the main "
        "bottleneck, at-risk orders and recommended actions.",
    ),
    "weekly": (
        "Weekly Production Plan",
        "The rolling weekly production outlook and the KPIs driving it.",
    ),
    "daily_progress": (
        "Daily Progress Report",
        "Progress against today's committed plan and the current KPIs.",
    ),
    "gantt_orders": (
        "Order Schedule (Gantt) Summary",
        "How orders are sequenced across the day, with timing and any late "
        "orders highlighted.",
    ),
    "gantt_machines": (
        "Machine Schedule (Gantt) Summary",
        "How work is distributed across machines, with the busiest resources "
        "highlighted.",
    ),
    "machines": (
        "Machine Load Summary",
        "Scheduled load per machine for the day, busiest first.",
    ),
    "orders": (
        "Scheduled Orders Summary",
        "The orders scheduled for the day, including any at risk of being late.",
    ),
    "deliveries": (
        "Delivery Outlook",
        "The delivery outlook for open orders and their on-time status.",
    ),
    "drift": (
        "Delivery Drift Report",
        "How delivery dates have drifted versus the prior plan.",
    ),
    "scenarios": (
        "Scenario Comparison",
        "How alternative what-if plans compare to the committed baseline.",
    ),
    "risks": (
        "Operational Risk Summary",
        "The operational risks detected for the day and the recommended fixes.",
    ),
    "current_plan": (
        "Current Committed Plan",
        "A summary of the plan currently committed for the day.",
    ),
    "live_ops": (
        "Live Operations Status",
        "The current live shop-floor status and today's headline KPIs.",
    ),
}


def _pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "—"


def _minutes(value: float | int | None) -> str:
    if value is None:
        return "—"
    total = int(value)
    days, rem = divmod(total, 1440)
    hours, mins = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts)


def _currency(value: float | None) -> str:
    return f"${value:,.0f}" if value is not None else "—"


def _kpi_grid(kpis: KpiSet) -> str:
    cards = [
        ("On-Time Delivery", _pct(kpis.on_time_delivery_rate)),
        ("Avg Machine Utilization", _pct(kpis.average_machine_utilization)),
        ("Total Tardiness", _minutes(kpis.total_tardiness_minutes)),
        ("Makespan", _minutes(kpis.metrics.get("makespan_minutes"))),
        ("Scheduled Orders", str(int(kpis.metrics.get("scheduled_orders", 0)))),
        ("Est. Plan Cost", _currency(kpis.metrics.get("cost_total"))),
    ]
    cells = "".join(
        f'<td style="padding:6px;">'
        f'<div style="border:1px solid {_BORDER};border-radius:10px;padding:12px 14px;">'
        f'<div style="font-size:20px;font-weight:700;color:{_INK};">{escape(value)}</div>'
        f'<div style="font-size:12px;color:{_MUTED};margin-top:2px;">{escape(label)}</div>'
        f"</div></td>"
        + ("</tr><tr>" if (i % 3 == 2) else "")
        for i, (label, value) in enumerate(cards)
    )
    return (
        f'<table style="width:100%;border-collapse:collapse;margin-bottom:8px;">'
        f"<tr>{cells}</tr></table>"
    )


def _bullets(items: list[str]) -> str:
    lis = "".join(f'<li style="margin:4px 0;">{i}</li>' for i in items)
    return f'<ul style="margin:8px 0 0;padding-left:18px;font-size:14px;">{lis}</ul>'


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return f'<p style="color:{_MUTED};">No data available.</p>'
    head = "".join(
        f'<th style="text-align:left;padding:8px 10px;border-bottom:2px solid {_BORDER};'
        f'font-size:12px;color:{_MUTED};text-transform:uppercase;letter-spacing:.04em;">'
        f"{escape(h)}</th>"
        for h in headers
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td style="padding:8px 10px;border-bottom:1px solid {_BORDER};font-size:14px;">'
            f"{escape(str(c))}</td>"
            for c in row
        )
        + "</tr>"
        for row in rows
    )
    return (
        f'<table style="width:100%;border-collapse:collapse;border:1px solid {_BORDER};'
        f'border-radius:10px;overflow:hidden;"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table>"
    )


def _section(title: str, inner: str) -> str:
    return (
        f'<div style="margin-top:20px;">'
        f'<div style="font-size:13px;font-weight:700;color:{_PRIMARY};'
        f'text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">{escape(title)}</div>'
        f"{inner}</div>"
    )


def _specific_section(report_type: str, s: ExplanationSummary) -> str:
    """Build the report-type-specific content block from the summary."""
    if report_type == "scenarios":
        rows = [
            [
                sc.name + (" (baseline)" if sc.is_baseline else ""),
                _minutes(sc.kpis.get("makespan_minutes")),
                _pct(sc.kpis.get("on_time_delivery_rate")),
            ]
            for sc in s.scenarios.scenarios
        ]
        best = s.scenarios.best_makespan_scenario
        note = (
            _bullets([f"Best makespan scenario: <strong>{escape(best)}</strong>"])
            if best
            else ""
        )
        return _section(
            "Scenario comparison",
            _table(["Scenario", "Makespan", "On-time"], rows) + note,
        )

    if report_type in ("machines", "gantt_machines"):
        rows = [
            [m.machine_id, _minutes(m.scheduled_minutes), str(m.operations)]
            for m in s.machine_load[:10]
        ]
        return _section(
            "Busiest machines", _table(["Machine", "Scheduled load", "Ops"], rows)
        )

    if report_type in ("orders", "gantt_orders", "deliveries", "drift"):
        rows = [
            [
                lo.order_id,
                _minutes(lo.tardiness_minutes),
                lo.due_date or "—",
                ", ".join(lo.machines[:3]) or "—",
            ]
            for lo in s.late_orders[:10]
        ]
        heading = "Late / at-risk orders" if rows else "Orders"
        inner = (
            _table(["Order", "Tardiness", "Due", "Machines"], rows)
            if rows
            else _bullets(
                [
                    f"Scheduled orders: <strong>{s.schedule.scheduled_orders}</strong>",
                    f"Operations: <strong>{s.schedule.scheduled_operations}</strong>",
                    "No orders are currently flagged late.",
                ]
            )
        )
        return _section(heading, inner)

    if report_type == "risks":
        cards = []
        for r in s.risks.top[:8]:
            color = _SEVERITY_COLOR.get(r.severity, _MUTED)
            cards.append(
                f'<div style="border:1px solid {_BORDER};border-left:4px solid {color};'
                f'border-radius:10px;padding:12px 14px;margin-bottom:10px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="font-weight:700;">{escape(r.title)}</span>'
                f"{_chip(r.severity.title(), color)}</div>"
                f'<div style="font-size:13px;color:{_INK};margin-top:4px;">'
                f"{escape(r.description)}</div></div>"
            )
        return _section(
            f"Top risks ({s.risks.total} total)", "".join(cards) or "No risks."
        )

    # overview + default: headline bullets from the summary.
    bottleneck = s.machine_load[0] if s.machine_load else None
    items = [
        f"Plan status: <strong>{escape(s.schedule.status)}</strong> "
        f"({s.schedule.scheduled_operations} ops)",
        f"Bottleneck: <strong>{escape(bottleneck.machine_id)}</strong> "
        f"({_minutes(bottleneck.scheduled_minutes)} load)"
        if bottleneck
        else "Bottleneck: none",
        f"Risks detected: <strong>{s.risks.total}</strong>",
        f"Late orders: <strong>{len(s.late_orders)}</strong>",
        f"Recommended fixes: <strong>{s.recommendations.total}</strong>",
    ]
    return _section("Headlines", _bullets(items))


def render_report_email(
    report_type: str,
    business_date: str,
    summary: ExplanationSummary,
    kpis: KpiSet,
    *,
    role: str | None = None,
) -> tuple[str, str, str]:
    """Render a professional per-tab report email; returns ``(subject, html, text)``."""
    title, what_is = REPORT_META.get(
        report_type, ("Production Report", "A production planning report.")
    )
    role_line = (
        f'<div style="margin-bottom:12px;">{_chip("Prepared for: " + role, _PRIMARY)}</div>'
        if role
        else ""
    )
    intro = (
        f"{escape(what_is)} This report is for "
        f"<strong>{escape(business_date)}</strong>."
    )
    body = role_line + _kpi_grid(kpis) + _specific_section(report_type, summary)
    html = _shell(title, intro, body)
    subject = f"[PPO] {title} — {business_date}" + (f" · {role}" if role else "")

    text_lines = [f"{title} for {business_date}", "", what_is, ""]
    text_lines.append(f"On-time delivery: {_pct(kpis.on_time_delivery_rate)}")
    text_lines.append(f"Avg machine utilization: {_pct(kpis.average_machine_utilization)}")
    text_lines.append(f"Total tardiness: {_minutes(kpis.total_tardiness_minutes)}")
    return subject, html, "\n".join(text_lines)
