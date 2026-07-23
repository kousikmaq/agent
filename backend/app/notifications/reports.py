"""Per-tab report email rendering.

Turns the persisted, deterministic results (curated ExplanationSummary + KpiSet)
into professional, self-contained HTML emails - one tailored report per UI tab
(overview, weekly, orders, scenarios, machines, ...). Content is addressed to a
named operational role so the recipient immediately understands the context.

Reuses the shared email shell/helpers from :mod:`app.notifications.templates`.
"""

from __future__ import annotations

from html import escape
from typing import Any

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
    "materials": (
        "Materials Availability",
        "Material stock levels and any shortages against reorder / safety, with "
        "the items that need replenishing.",
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
        + ("</tr><tr>" if (i % 3 == 2 and i != len(cards) - 1) else "")
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


_GOOD = "#16a34a"
_WARN = "#f59e0b"
_BAD = "#ef4444"


def _note(text: str) -> str:
    return (
        f'<p style="font-size:13px;color:{_INK};line-height:1.5;margin:0 0 10px;">'
        f"{text}</p>"
    )


def _weekly_section(s: ExplanationSummary, context: dict[str, Any]) -> str:
    w = context.get("weekly")
    if w is None:
        return _section("Weekly plan", _note("Weekly plan is not available yet."))
    head = _bullets(
        [
            f"Week: <strong>{escape(str(w.week_start))} → {escape(str(w.week_end))}</strong>",
            f"Overall status: <strong>{escape(str(w.overall_status))}</strong>",
            f"Attainment to date: <strong>{_pct(w.attainment_to_date)}</strong>",
            f"Planned this week: <strong>{w.planned_operations}</strong> operations, "
            f"<strong>{w.planned_units}</strong> units",
        ]
    )
    rows = [
        [
            f"{d.weekday} {d.date}",
            str(d.planned_operations),
            str(d.planned_units),
            str(d.actual_operations) if d.actual_operations is not None else "—",
            _pct(d.attainment) if d.attainment is not None else "—",
            str(d.status),
        ]
        for d in w.days
    ]
    return _section(
        "Weekly production plan",
        head
        + _table(
            ["Day", "Planned ops", "Planned units", "Actual ops", "Attainment", "Status"],
            rows,
        ),
    )


def _progress_section(context: dict[str, Any]) -> str:
    w = context.get("weekly")
    if w is None:
        return _section("Daily progress", _note("Progress data is not available yet."))
    head = _bullets(
        [
            f"Planned to date: <strong>{w.planned_to_date_operations}</strong> ops "
            f"({w.planned_to_date_units} units)",
            f"Actual to date: <strong>{w.actual_to_date_operations}</strong> ops "
            f"({w.actual_to_date_units} units)",
            f"Attainment to date: <strong>{_pct(w.attainment_to_date)}</strong>",
        ]
    )
    rows = [
        [
            f"{d.weekday} {d.date}",
            str(d.planned_operations),
            str(d.actual_operations) if d.actual_operations is not None else "—",
            str(d.actual_units) if d.actual_units is not None else "—",
            _pct(d.attainment) if d.attainment is not None else "—",
            str(d.status),
        ]
        for d in w.days
        if d.is_past or d.is_today
    ]
    return _section(
        "Progress against today's plan",
        head
        + _table(
            ["Day", "Planned ops", "Actual ops", "Actual units", "Attainment", "Status"],
            rows,
        ),
    )


def _deliveries_section(s: ExplanationSummary, context: dict[str, Any]) -> str:
    d = context.get("deliveries")
    chips = ""
    if d is not None:
        chips = (
            '<div style="margin-bottom:10px;">'
            f'{_chip("On track: " + str(d.on_track), _GOOD)} '
            f'{_chip("At risk: " + str(d.at_risk), _WARN)} '
            f'{_chip("Late: " + str(d.late), _BAD)} '
            f'{_chip("Unscheduled: " + str(d.unscheduled), _MUTED)}</div>'
        )
    if d is not None and d.lines:
        rows = [
            [
                ln.order_id,
                str(ln.status).replace("_", " ").title(),
                ln.due_date or "—",
                _minutes(ln.tardiness_minutes) if ln.tardiness_minutes else "—",
            ]
            for ln in d.lines[:15]
        ]
        table = _table(["Order", "Status", "Due", "Late by"], rows)
    else:
        rows = [
            [lo.order_id, _minutes(lo.tardiness_minutes), lo.due_date or "—"]
            for lo in s.late_orders[:15]
        ]
        table = _table(["Order", "Tardiness", "Due"], rows)
    return _section("Orders & delivery status", chips + table)


def _drift_section(s: ExplanationSummary, context: dict[str, Any]) -> str:
    drift = context.get("drift")
    if drift is not None:
        chips = (
            '<div style="margin-bottom:10px;">'
            f'{_chip("Slipping: " + str(drift.slipping), _BAD)} '
            f'{_chip("Improving: " + str(drift.improving), _GOOD)} '
            f'{_chip("Stable: " + str(drift.stable), _MUTED)} '
            f'{_chip("New: " + str(drift.new), _PRIMARY)}</div>'
        )
        rows = [
            [
                ln.order_id,
                str(ln.trend).title(),
                _minutes(abs(ln.delta_minutes)) if ln.delta_minutes else "—",
                str(ln.current_status).replace("_", " ").title(),
            ]
            for ln in drift.lines[:15]
        ]
        return _section(
            "Delivery drift vs the prior plan",
            _note(
                "How each order's completion has moved since the previous plan "
                "(a positive drift means it is finishing later)."
            )
            + chips
            + _table(["Order", "Trend", "Drift", "Status"], rows),
        )
    return _deliveries_section(s, context)


def _materials_section(context: dict[str, Any]) -> str:
    m = context.get("materials")
    if m is None:
        return _section("Materials", _note("Materials data is not available."))
    chips = (
        '<div style="margin-bottom:10px;">'
        f'{_chip("Below safety: " + str(m.below_safety), _BAD)} '
        f'{_chip("Below reorder: " + str(m.below_reorder), _WARN)} '
        f'{_chip("Tracked: " + str(m.total), _MUTED)}</div>'
    )
    short = [ln for ln in m.lines if ln.below_reorder or ln.below_safety][:15]
    rows = [
        [
            f"{ln.product_id}" + (f" ({ln.name})" if ln.name else ""),
            f"{ln.net_available:g}",
            f"{ln.reorder_point:g}",
            f"{ln.safety_stock:g}",
            f"{ln.shortage:g}" if ln.shortage else "—",
            "Below safety" if ln.below_safety else "Below reorder",
        ]
        for ln in short
    ]
    table = (
        _table(
            ["Material", "Net avail", "Reorder", "Safety", "Shortage", "Status"], rows
        )
        if rows
        else _note("All tracked materials are above their reorder points.")
    )
    return _section("Materials running low", chips + table)


def _scenario_section(s: ExplanationSummary, context: dict[str, Any]) -> str:
    scenarios = s.scenarios.scenarios
    if not scenarios:
        return _section("Scenario", _note("No scenario data available."))
    scenario_type = context.get("scenario_type")
    sel = next((sc for sc in scenarios if sc.scenario_type == scenario_type), None)
    if sel is None:
        sel = next((sc for sc in scenarios if sc.is_baseline), scenarios[0])
    perf = _table(
        ["Metric", "Value"],
        [
            ["On-time delivery", _pct(sel.kpis.get("on_time_delivery_rate"))],
            ["Makespan", _minutes(sel.kpis.get("makespan_minutes"))],
            ["Total tardiness", _minutes(sel.kpis.get("total_tardiness_minutes"))],
        ],
    )
    cost = _table(
        ["Cost component", "Amount"],
        [
            ["Total estimated cost", _currency(sel.kpis.get("cost_total"))],
            ["Labour (regular)", _currency(sel.kpis.get("cost_labor_regular"))],
            ["Labour (overtime)", _currency(sel.kpis.get("cost_labor_overtime"))],
            ["Machine running", _currency(sel.kpis.get("cost_machine"))],
            ["Late-delivery penalty", _currency(sel.kpis.get("cost_tardiness_penalty"))],
        ],
    )
    name = escape(sel.name) + (" (baseline)" if sel.is_baseline else "")
    return _section(
        f"Scenario: {name}",
        _section("Performance", perf) + _section("Cost breakdown", cost),
    )


def _risks_section(s: ExplanationSummary) -> str:
    chips = " ".join(
        _chip(f"{sev.title()}: {n}", _SEVERITY_COLOR.get(sev, _MUTED))
        for sev, n in s.risks.by_severity.items()
    )
    cards = []
    for r in s.risks.top[:5]:
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
    rest = s.risks.top[5:]
    more = ""
    if rest:
        items = [
            f"{escape(r.title)} <em style='color:{_MUTED};'>({r.severity.title()})</em>"
            for r in rest
        ]
        more = _section(f"More risks ({len(rest)})", _bullets(items))
    return _section(
        f"Risk summary ({s.risks.total} total)",
        f'<div style="margin-bottom:12px;">{chips}</div>' + "".join(cards) + more,
    )


def _current_plan_section(s: ExplanationSummary, context: dict[str, Any]) -> str:
    mods = context.get("modifications")
    if mods is None:
        return _section(
            "Current plan", _note("This plan matches the originally planned schedule.")
        )
    metric_rows = []
    for key, label, fmt in (
        ("makespan_minutes", "Makespan", _minutes),
        ("total_tardiness_minutes", "Total tardiness", _minutes),
        ("on_time_delivery_rate", "On-time delivery", _pct),
        ("cost_total", "Estimated cost", _currency),
    ):
        before = mods.baseline_kpis.get(key)
        after = mods.current_kpis.get(key)
        metric_rows.append([label, fmt(before), fmt(after)])
    comparison = _table(["Metric", "Original", "Current"], metric_rows)
    mod_items = [
        f"{escape(m.label)} <em style='color:{_MUTED};'>({m.applied_at.replace('T', ' ')})</em>"
        for m in mods.modifications
    ]
    mods_block = (
        _section(f"Modifications applied ({len(mods.modifications)})", _bullets(mod_items))
        if mod_items
        else ""
    )
    return _section("Original plan → current plan", comparison) + mods_block


def _live_ops_section(context: dict[str, Any]) -> str:
    sf = context.get("shopfloor")
    if sf is None:
        return _section("Live status", _note("Live status is not available."))
    machines = _bullets(
        [
            f"Available: <strong>{sf.machine_available}</strong> · "
            f"Running: <strong>{sf.machine_running}</strong> · "
            f"Idle: <strong>{sf.machine_idle}</strong> · "
            f"Down: <strong>{sf.machine_down}</strong> · "
            f"Maintenance: <strong>{sf.machine_maintenance}</strong>",
        ]
    )
    workers = _bullets(
        [
            f"Available: <strong>{sf.worker_available}</strong> of "
            f"<strong>{sf.worker_total}</strong> "
            f"({sf.worker_unavailable} unavailable)",
        ]
    )
    orders = _bullets(
        [
            f"In progress: <strong>{sf.orders_in_progress}</strong> · "
            f"Released: <strong>{sf.orders_released}</strong> · "
            f"Planned: <strong>{sf.orders_planned}</strong> · "
            f"Completed: <strong>{sf.orders_completed}</strong>",
        ]
    )
    materials = _bullets(
        [
            f"Below reorder: <strong>{sf.materials_below_reorder}</strong> · "
            f"Below safety: <strong>{sf.materials_below_safety}</strong>",
        ]
    )
    return (
        _section("Machines", machines)
        + _section("Workforce", workers)
        + _section("Orders", orders)
        + _section("Materials", materials)
    )


def _specific_section(
    report_type: str, s: ExplanationSummary, context: dict[str, Any]
) -> str:
    """Build the report-type-specific content block."""
    if report_type == "weekly":
        return _weekly_section(s, context)
    if report_type == "daily_progress":
        return _progress_section(context)
    if report_type == "gantt_machines":
        rows = [
            [m.machine_id, _minutes(m.scheduled_minutes), str(m.operations)]
            for m in s.machine_load[:12]
        ]
        return _section(
            "Machine schedule (Gantt)",
            _note(
                "The machine Gantt has one row per machine and a coloured bar for "
                "each operation across the day (left = earlier, right = later). It "
                "shows how work is spread across machines and which are busiest. "
                "The scheduled load per machine is listed below."
            )
            + _table(["Machine", "Scheduled load", "Ops"], rows),
        )
    if report_type == "gantt_orders":
        rows = [
            [
                lo.order_id,
                _minutes(lo.tardiness_minutes),
                lo.due_date or "—",
                ", ".join(lo.machines[:3]) or "—",
            ]
            for lo in s.late_orders[:12]
        ]
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
        return _section(
            "Order schedule (Gantt)",
            _note(
                "The order Gantt has one row per order and a coloured bar for each "
                "of its operations as it flows across machines through the day. It "
                "shows how each order progresses and where delays build up. Any "
                "orders flagged late are listed below."
            )
            + inner,
        )
    if report_type == "machines":
        rows = [
            [m.machine_id, _minutes(m.scheduled_minutes), str(m.operations)]
            for m in s.machine_load[:12]
        ]
        return _section(
            "Busiest machines", _table(["Machine", "Scheduled load", "Ops"], rows)
        )
    if report_type in ("orders", "deliveries"):
        return _deliveries_section(s, context)
    if report_type == "drift":
        return _drift_section(s, context)
    if report_type == "materials":
        return _materials_section(context)
    if report_type == "scenarios":
        return _scenario_section(s, context)
    if report_type == "risks":
        return _risks_section(s)
    if report_type == "current_plan":
        return _current_plan_section(s, context)
    if report_type == "live_ops":
        return _live_ops_section(context)

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


# Report types that render their own headline metrics (skip the generic grid).
_NO_KPI_GRID = {"scenarios", "live_ops", "materials"}


def render_report_email(
    report_type: str,
    business_date: str,
    summary: ExplanationSummary,
    kpis: KpiSet,
    *,
    role: str | None = None,
    context: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """Render a professional per-tab report email; returns ``(subject, html, text)``."""
    context = context or {}
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
    kpi_grid = "" if report_type in _NO_KPI_GRID else _kpi_grid(kpis)
    body = role_line + kpi_grid + _specific_section(report_type, summary, context)
    html = _shell(title, intro, body)
    subject = f"[PPO] {title} — {business_date}" + (f" · {role}" if role else "")

    text_lines = [f"{title} for {business_date}", "", what_is, ""]
    text_lines.append(f"On-time delivery: {_pct(kpis.on_time_delivery_rate)}")
    text_lines.append(f"Avg machine utilization: {_pct(kpis.average_machine_utilization)}")
    text_lines.append(f"Total tardiness: {_minutes(kpis.total_tardiness_minutes)}")
    return subject, html, "\n".join(text_lines)
