"""Detector: delayed orders.

Flags every scheduled order that completes after the end of its due date, with
severity scaled by how many days late it is.
"""

from __future__ import annotations

import math

from app.domain.enums import RiskSeverity, RiskType
from app.risk.result import RiskBuilder, RiskContext

_MINUTES_PER_DAY = 1440


def _severity(tardiness_minutes: int) -> RiskSeverity:
    days = tardiness_minutes / _MINUTES_PER_DAY
    if days > 5:
        return RiskSeverity.CRITICAL
    if days > 2:
        return RiskSeverity.HIGH
    if days >= 1:
        return RiskSeverity.MEDIUM
    return RiskSeverity.LOW


def detect(ctx: RiskContext, builder: RiskBuilder) -> None:
    """Emit a DELAYED_ORDER risk for each late order."""
    for outcome in ctx.aggregates.order_outcomes:
        if outcome.on_time:
            continue
        days_late = math.ceil(outcome.tardiness_minutes / _MINUTES_PER_DAY)
        builder.add(
            risk_type=RiskType.DELAYED_ORDER,
            severity=_severity(outcome.tardiness_minutes),
            title=f"Order {outcome.order_id} is {days_late} day(s) late",
            description=(
                f"Order {outcome.order_id} ({outcome.product_id}) is scheduled to "
                f"complete {outcome.tardiness_minutes} minute(s) after its due date "
                f"{outcome.due_date.isoformat()}."
            ),
            affected_entities={"order_ids": [outcome.order_id]},
            evidence={
                "due_date": outcome.due_date.isoformat(),
                "completion": outcome.completion.isoformat() if outcome.completion else None,
                "tardiness_minutes": outcome.tardiness_minutes,
                "priority": outcome.priority,
            },
        )
