"""HTML email templates for the agentic actions.

Pure functions that render professional, self-contained HTML (inline styles, as
required by most email clients) plus a plain-text fallback. All dynamic content
is HTML-escaped to avoid injection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from app.domain.models.recommendation import Recommendation, RecommendationSet
from app.domain.models.risk import Risk, RiskReport

# Brand palette (kept light/professional to match the app).
_PRIMARY = "#2563eb"
_INK = "#0f172a"
_MUTED = "#64748b"
_BORDER = "#e2e8f0"
_BG = "#f8fafc"

_SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
_SEVERITY_COLOR = {
    "CRITICAL": "#dc2626",
    "HIGH": "#ea580c",
    "MEDIUM": "#ca8a00",
    "LOW": "#0891b2",
}


def _shell(title: str, intro: str, body: str) -> str:
    """Wrap content in a consistent, email-safe HTML shell."""
    year = datetime.now(timezone.utc).year
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:{_BG};font-family:Segoe UI,Arial,sans-serif;color:{_INK};">
    <div style="max-width:680px;margin:0 auto;padding:24px;">
      <div style="background:#ffffff;border:1px solid {_BORDER};border-radius:14px;overflow:hidden;">
        <div style="background:{_PRIMARY};padding:20px 24px;">
          <div style="color:#fff;font-size:13px;letter-spacing:.08em;text-transform:uppercase;opacity:.85;">
            Production Planning &amp; Schedule Optimization
          </div>
          <div style="color:#fff;font-size:22px;font-weight:700;margin-top:4px;">{escape(title)}</div>
        </div>
        <div style="padding:24px;">
          <p style="margin:0 0 18px;color:{_MUTED};font-size:15px;line-height:1.5;">{intro}</p>
          {body}
        </div>
        <div style="padding:16px 24px;border-top:1px solid {_BORDER};color:{_MUTED};font-size:12px;">
          Sent automatically by the PPO Agent · {year}. This is an operational
          notification generated from the deterministic planning results.
        </div>
      </div>
    </div>
  </body>
</html>"""


def _chip(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'background:{color}1a;color:{color};font-size:12px;font-weight:700;">'
        f"{escape(text)}</span>"
    )


def _summarize_entities(entities: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for key, values in entities.items():
        if not values:
            continue
        label = key.replace("_", " ").rstrip("s")
        shown = ", ".join(values[:4]) + ("…" if len(values) > 4 else "")
        parts.append(f"{escape(label)}: {escape(shown)}")
    return " · ".join(parts)


def _recs_for(risk: Risk, recs: list[Recommendation]) -> list[Recommendation]:
    return [r for r in recs if risk.risk_id in r.addresses_risk_ids]


def render_risk_email(
    business_date: str,
    report: RiskReport,
    recommendations: RecommendationSet | None,
    *,
    severities: list[str] | None = None,
) -> tuple[str, str, str]:
    """Render the risk-summary email; returns ``(subject, html, text)``."""
    recs = recommendations.recommendations if recommendations else []
    risks = report.risks
    if severities:
        wanted = {s.upper() for s in severities}
        risks = [r for r in risks if r.severity.value in wanted]

    order = {s: i for i, s in enumerate(_SEVERITY_ORDER)}
    risks = sorted(risks, key=lambda r: (order.get(r.severity.value, 99), r.risk_id))

    counts = {s: sum(1 for r in risks if r.severity.value == s) for s in _SEVERITY_ORDER}
    summary_chips = "".join(
        f'<td style="padding:0 8px 0 0;">{_chip(f"{counts[s]} {s.title()}", _SEVERITY_COLOR[s])}</td>'
        for s in _SEVERITY_ORDER
        if counts[s]
    ) or f'<td style="color:{_MUTED};">No open risks.</td>'

    cards: list[str] = []
    for risk in risks:
        color = _SEVERITY_COLOR.get(risk.severity.value, _MUTED)
        entities = _summarize_entities(risk.affected_entities)
        rec_html = ""
        matched = _recs_for(risk, recs)
        if matched:
            items = "".join(
                f'<li style="margin:2px 0;">{escape(r.title)} '
                f'<span style="color:{_MUTED};">({escape(r.feasibility.value.replace("_", " ").title())})</span></li>'
                for r in matched[:3]
            )
            rec_html = (
                f'<div style="margin-top:10px;padding:10px 12px;background:{_BG};'
                f'border-radius:8px;font-size:13px;">'
                f'<div style="color:{_MUTED};text-transform:uppercase;letter-spacing:.06em;'
                f'font-size:11px;margin-bottom:4px;">Recommended actions</div>'
                f'<ul style="margin:0;padding-left:18px;">{items}</ul></div>'
            )
        cards.append(
            f'<div style="border:1px solid {_BORDER};border-left:4px solid {color};'
            f'border-radius:10px;padding:14px 16px;margin-bottom:12px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div style="font-weight:700;font-size:15px;">{escape(risk.title)}</div>'
            f"{_chip(risk.severity.value.title(), color)}</div>"
            f'<div style="margin:6px 0 0;font-size:14px;line-height:1.5;color:{_INK};">'
            f"{escape(risk.description)}</div>"
            + (
                f'<div style="margin-top:6px;color:{_MUTED};font-size:12px;">{entities}</div>'
                if entities
                else ""
            )
            + rec_html
            + "</div>"
        )

    body = (
        f'<table style="margin-bottom:16px;"><tr>{summary_chips}</tr></table>'
        + ("".join(cards) if cards else f'<p style="color:{_MUTED};">No risks match the current filter.</p>')
    )
    intro = (
        f"Risk summary for <strong>{escape(business_date)}</strong>. "
        f"{len(risks)} risk(s) included below, ordered by severity."
    )
    subject = f"[PPO] Risk summary for {business_date} — {len(risks)} risk(s)"
    html = _shell("Operational Risk Summary", intro, body)

    text_lines = [f"Risk summary for {business_date} ({len(risks)} risks)", ""]
    for risk in risks:
        text_lines.append(f"[{risk.severity.value}] {risk.title}")
        text_lines.append(f"    {risk.description}")
    text = "\n".join(text_lines)
    return subject, html, text


def render_purchase_order_email(
    *,
    item: str,
    quantity: str,
    supplier: str | None = None,
    order_id: str | None = None,
    needed_by: str | None = None,
    reason: str | None = None,
    requested_by: str = "Production Planning Team",
) -> tuple[str, str, str]:
    """Render a professional purchase-order request; returns ``(subject, html, text)``."""
    rows = [
        ("Item / Material", item),
        ("Quantity", quantity),
        ("Supplier", supplier or "To be assigned by Procurement"),
        ("Linked order", order_id or "—"),
        ("Needed by", needed_by or "At earliest availability"),
    ]
    row_html = "".join(
        f'<tr>'
        f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};color:{_MUTED};'
        f'font-size:13px;width:40%;">{escape(label)}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};font-weight:600;'
        f'font-size:14px;">{escape(value)}</td></tr>'
        for label, value in rows
    )
    reason_html = (
        f'<p style="margin:16px 0 0;font-size:14px;line-height:1.6;">'
        f'<strong>Justification:</strong> {escape(reason)}</p>'
        if reason
        else ""
    )
    body = (
        f'<table style="width:100%;border-collapse:collapse;border:1px solid {_BORDER};'
        f'border-radius:10px;overflow:hidden;">{row_html}</table>'
        + reason_html
        + f'<p style="margin:18px 0 0;font-size:14px;color:{_MUTED};">'
        f"Please confirm availability and expected delivery date. Requested by "
        f"{escape(requested_by)}.</p>"
    )
    intro = (
        "A material replenishment is requested to keep the production schedule on "
        "track. Details are below."
    )
    subject = f"[PPO] Purchase order request — {item}" + (
        f" (for {order_id})" if order_id else ""
    )
    html = _shell("Purchase Order Request", intro, body)

    text = (
        "Purchase order request\n\n"
        + "\n".join(f"{label}: {value}" for label, value in rows)
        + (f"\n\nJustification: {reason}" if reason else "")
    )
    return subject, html, text
