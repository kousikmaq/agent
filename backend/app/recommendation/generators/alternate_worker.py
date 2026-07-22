"""Generator: assign an alternate worker.

Addresses worker conflicts (double bookings and unstaffed skilled operations) by
proposing another available, qualified worker. When no qualified worker exists,
the recommendation is flagged as requiring approval (training/hiring).
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


def generate(ctx: RecommendationContext, builder: RecommendationBuilder) -> None:
    """Propose alternate-worker assignments for worker-conflict risks."""
    operation_by_id = {
        op.operation_id: op
        for routing in ctx.state.routings
        for op in routing.operations
    }

    for risk in ctx.risk_report.risks:
        if risk.risk_type is not RiskType.WORKER_CONFLICT:
            continue

        # Determine the skill involved from the operation(s) referenced.
        skills: set[str] = set()
        required_skill = risk.evidence.get("required_skill")
        if required_skill:
            skills.add(required_skill)
        for operation_id in risk.affected_entities.get("operation_ids", []):
            operation = operation_by_id.get(operation_id)
            if operation and operation.required_skill:
                skills.add(operation.required_skill)

        candidates: list[str] = []
        already = set(risk.affected_entities.get("worker_ids", []))
        for skill in skills:
            for worker_id in ctx.skill_to_workers.get(skill, []):
                if worker_id not in already and worker_id not in candidates:
                    candidates.append(worker_id)

        if candidates:
            feasibility = RecommendationFeasibility.FEASIBLE
            description = (
                f"Reassign the affected operation(s) to an available qualified "
                f"worker: {', '.join(candidates[:3])}."
            )
        else:
            feasibility = RecommendationFeasibility.REQUIRES_APPROVAL
            description = (
                "No available qualified worker exists; approve overtime, training, "
                "or temporary staffing to cover the required skill."
            )

        builder.add(
            action=RecommendationAction.ASSIGN_ALTERNATE_WORKER,
            addresses_risk_ids=[risk.risk_id],
            title="Assign an alternate worker to resolve the conflict",
            description=description,
            target_entities={
                "operation_ids": risk.affected_entities.get("operation_ids", []),
                "candidate_worker_ids": candidates[:3],
            },
            expected_impact={"candidate_workers": candidates[:3], "skills": sorted(skills)},
            feasibility=feasibility,
            priority=priority_from_severity(risk.severity),
        )
