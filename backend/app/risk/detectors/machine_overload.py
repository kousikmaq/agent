"""Detector: machine overload.

Flags machines whose scheduled busy time meets or exceeds their available time
on the business date, indicating the machine is a bottleneck.
"""

from __future__ import annotations

from app.domain.enums import RiskSeverity, RiskType
from app.risk.result import RiskBuilder, RiskContext

# Utilisation at/above this fraction is considered overloaded.
_OVERLOAD_THRESHOLD = 0.9


def _severity(ratio: float) -> RiskSeverity:
    if ratio >= 1.5:
        return RiskSeverity.CRITICAL
    if ratio >= 1.2:
        return RiskSeverity.HIGH
    if ratio >= 1.0:
        return RiskSeverity.MEDIUM
    return RiskSeverity.LOW


def detect(ctx: RiskContext, builder: RiskBuilder) -> None:
    """Emit a MACHINE_OVERLOAD risk for oversubscribed machines."""
    for usage in ctx.aggregates.machine_usage:
        if usage.available_minutes <= 0 or usage.busy_minutes <= 0:
            continue
        ratio = usage.busy_minutes / usage.available_minutes
        if ratio < _OVERLOAD_THRESHOLD:
            continue
        builder.add(
            risk_type=RiskType.MACHINE_OVERLOAD,
            severity=_severity(ratio),
            title=f"Machine {usage.machine_id} is overloaded ({ratio:.0%})",
            description=(
                f"Machine {usage.machine_id} is scheduled for {usage.busy_minutes} "
                f"minute(s) against {usage.available_minutes} available minute(s) "
                f"on the business date."
            ),
            affected_entities={"machine_ids": [usage.machine_id]},
            evidence={
                "busy_minutes": usage.busy_minutes,
                "available_minutes": usage.available_minutes,
                "utilization_ratio": round(ratio, 4),
            },
        )
