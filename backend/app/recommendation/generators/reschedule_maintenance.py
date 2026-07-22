"""Generator: reschedule maintenance.

Addresses maintenance conflicts and machine overload by proposing to move a
movable (planned/preventive) maintenance window off the machine's peak period,
freeing capacity.
"""

from __future__ import annotations

from app.domain.enums import (
    RecommendationAction,
    RecommendationFeasibility,
    RiskType,
)
from app.recommendation.result import (
    RecommendationBuilder,
    RecommendationContext,
    priority_from_severity,
)

_RELEVANT = {RiskType.MAINTENANCE_CONFLICT, RiskType.MACHINE_OVERLOAD}


def generate(ctx: RecommendationContext, builder: RecommendationBuilder) -> None:
    """Propose rescheduling movable maintenance on affected machines."""
    for risk in ctx.risk_report.risks:
        if risk.risk_type not in _RELEVANT:
            continue
        for machine_id in risk.affected_entities.get("machine_ids", []):
            windows = ctx.movable_maintenance_by_machine.get(machine_id)
            if not windows:
                continue
            maintenance_ids = [w.maintenance_id for w in windows]
            builder.add(
                action=RecommendationAction.RESCHEDULE_MAINTENANCE,
                addresses_risk_ids=[risk.risk_id],
                title=f"Reschedule maintenance on {machine_id}",
                description=(
                    f"Move planned/preventive maintenance ({', '.join(maintenance_ids)}) "
                    f"on {machine_id} to a lower-demand window to free capacity."
                ),
                target_entities={
                    "machine_ids": [machine_id],
                    "maintenance_ids": maintenance_ids,
                },
                expected_impact={"movable_maintenance": maintenance_ids},
                feasibility=RecommendationFeasibility.REQUIRES_APPROVAL,
                priority=priority_from_severity(risk.severity),
            )
