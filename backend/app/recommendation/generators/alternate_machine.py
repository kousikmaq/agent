"""Generator: assign an alternate machine.

Addresses machine overload and maintenance conflicts by proposing to move work
to a less-loaded, usable machine in the same work center.
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

_RELEVANT = {RiskType.MACHINE_OVERLOAD, RiskType.MAINTENANCE_CONFLICT}


def generate(ctx: RecommendationContext, builder: RecommendationBuilder) -> None:
    """Propose alternate-machine reassignments for machine-bound risks."""
    for risk in ctx.risk_report.risks:
        if risk.risk_type not in _RELEVANT:
            continue
        for machine_id in risk.affected_entities.get("machine_ids", []):
            alternates = ctx.alternate_machines(machine_id)
            if not alternates:
                continue
            builder.add(
                action=RecommendationAction.ASSIGN_ALTERNATE_MACHINE,
                addresses_risk_ids=[risk.risk_id],
                title=f"Reassign work from {machine_id} to an alternate machine",
                description=(
                    f"Move part of {machine_id}'s load to a less-loaded machine in "
                    f"the same work center: {', '.join(alternates[:3])}."
                ),
                target_entities={
                    "machine_ids": [machine_id],
                    "alternate_machine_ids": alternates[:3],
                },
                expected_impact={
                    "relieves_machine": machine_id,
                    "candidate_machines": alternates[:3],
                },
                feasibility=RecommendationFeasibility.FEASIBLE,
                priority=priority_from_severity(risk.severity),
            )
