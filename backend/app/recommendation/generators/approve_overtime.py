"""Generator: approve overtime.

Addresses capacity shortages, delays, and worker conflicts by proposing to
approve overtime for eligible workers, adding effective capacity. Overtime
always requires management approval.
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

_RELEVANT = {
    RiskType.CAPACITY_SHORTAGE,
    RiskType.DELAYED_ORDER,
    RiskType.WORKER_CONFLICT,
}


def _overtime_eligible_worker_ids(ctx: RecommendationContext) -> list[str]:
    """Workers allowed to work overtime with a positive overtime allowance."""
    available_ids = {
        wid for workers in ctx.skill_to_workers.values() for wid in workers
    }
    return sorted(
        worker.worker_id
        for worker in ctx.state.workers
        if worker.overtime_allowed
        and worker.max_overtime_minutes_per_day > 0
        and worker.worker_id in available_ids
    )


def generate(ctx: RecommendationContext, builder: RecommendationBuilder) -> None:
    """Propose overtime approval for capacity/delay/worker risks."""
    eligible = _overtime_eligible_worker_ids(ctx)
    if not eligible:
        return

    for risk in ctx.risk_report.risks:
        if risk.risk_type not in _RELEVANT:
            continue

        targets: dict[str, list[str]] = {}
        if "work_centers" in risk.affected_entities:
            targets["work_centers"] = risk.affected_entities["work_centers"]
        if "order_ids" in risk.affected_entities:
            targets["order_ids"] = risk.affected_entities["order_ids"]
        if not targets:
            targets["work_centers"] = []

        builder.add(
            action=RecommendationAction.APPROVE_OVERTIME,
            addresses_risk_ids=[risk.risk_id],
            title="Approve overtime to add capacity",
            description=(
                "Approve overtime for eligible workers to increase effective "
                f"capacity ({len(eligible)} worker(s) eligible)."
            ),
            target_entities=targets,
            expected_impact={"eligible_worker_count": len(eligible)},
            feasibility=RecommendationFeasibility.REQUIRES_APPROVAL,
            priority=priority_from_severity(risk.severity),
        )
