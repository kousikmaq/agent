"""Recommendation context and set builder.

Shared, precomputed context passed to every generator, plus a builder that
deduplicates recommendations (merging the risks they address), assigns stable
ids, and produces the immutable :class:`RecommendationSet`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import (
    MachineStatus,
    MaintenanceType,
    PurchaseOrderStatus,
    RecommendationAction,
    RecommendationFeasibility,
    RiskSeverity,
    WorkerAvailabilityStatus,
)
from app.domain.models.factory_state import FactoryState
from app.domain.models.purchase_order import PurchaseOrder
from app.domain.models.recommendation import Recommendation, RecommendationSet
from app.domain.models.machine import MachineMaintenance
from app.domain.models.schedule import ScheduleResult
from app.domain.models.risk import RiskReport

# Purchase orders still expected to deliver stock.
_INBOUND_STATUSES = {
    PurchaseOrderStatus.OPEN,
    PurchaseOrderStatus.CONFIRMED,
    PurchaseOrderStatus.IN_TRANSIT,
    PurchaseOrderStatus.DELAYED,
}

# Maintenance that can realistically be rescheduled (unlike a breakdown).
_MOVABLE_MAINTENANCE = {MaintenanceType.PLANNED, MaintenanceType.PREVENTIVE}

_SEVERITY_PRIORITY = {
    RiskSeverity.CRITICAL: 10,
    RiskSeverity.HIGH: 8,
    RiskSeverity.MEDIUM: 5,
    RiskSeverity.LOW: 3,
}


def priority_from_severity(severity: RiskSeverity) -> int:
    """Map a risk severity to a recommendation priority (1-10)."""
    return _SEVERITY_PRIORITY.get(severity, 5)


@dataclass
class RecommendationContext:
    """Everything a generator needs, precomputed once."""

    state: FactoryState
    schedule: ScheduleResult
    risk_report: RiskReport
    machines_by_work_center: dict[str, list[str]] = field(default_factory=dict)
    machine_work_center: dict[str, str] = field(default_factory=dict)
    machine_busy_minutes: dict[str, int] = field(default_factory=dict)
    skill_to_workers: dict[str, list[str]] = field(default_factory=dict)
    order_by_id: dict[str, Any] = field(default_factory=dict)
    inbound_pos_by_product: dict[str, list[PurchaseOrder]] = field(default_factory=dict)
    suppliers_by_product: dict[str, set[str]] = field(default_factory=dict)
    all_supplier_ids: set[str] = field(default_factory=set)
    movable_maintenance_by_machine: dict[str, list[MachineMaintenance]] = field(
        default_factory=dict
    )

    def alternate_machines(self, machine_id: str) -> list[str]:
        """Usable machines in the same work center, least-loaded first."""
        work_center = self.machine_work_center.get(machine_id)
        if work_center is None:
            return []
        candidates = [
            m for m in self.machines_by_work_center.get(work_center, []) if m != machine_id
        ]
        return sorted(candidates, key=lambda m: self.machine_busy_minutes.get(m, 0))


def build_recommendation_context(
    state: FactoryState, schedule: ScheduleResult, risk_report: RiskReport
) -> RecommendationContext:
    """Assemble the :class:`RecommendationContext` deterministically."""
    machines_by_wc: dict[str, list[str]] = {}
    machine_work_center: dict[str, str] = {}
    for machine in state.machines:
        machine_work_center[machine.machine_id] = machine.work_center
        if machine.status != MachineStatus.DOWN:
            machines_by_wc.setdefault(machine.work_center, []).append(machine.machine_id)

    machine_busy: dict[str, int] = {}
    for op in schedule.scheduled_operations:
        minutes = int((op.end - op.start).total_seconds() // 60)
        machine_busy[op.machine_id] = machine_busy.get(op.machine_id, 0) + minutes

    # Available qualified workers per skill.
    unavailable = {
        rec.worker_id
        for rec in state.worker_availability
        if rec.status != WorkerAvailabilityStatus.AVAILABLE
    }
    skill_to_workers: dict[str, list[str]] = {}
    for skill in state.worker_skills:
        if skill.worker_id not in unavailable:
            skill_to_workers.setdefault(skill.skill, []).append(skill.worker_id)

    inbound_pos: dict[str, list[PurchaseOrder]] = {}
    suppliers_by_product: dict[str, set[str]] = {}
    for po in state.purchase_orders:
        suppliers_by_product.setdefault(po.product_id, set()).add(po.supplier_id)
        if po.status in _INBOUND_STATUSES:
            inbound_pos.setdefault(po.product_id, []).append(po)
    for pos in inbound_pos.values():
        pos.sort(key=lambda p: p.expected_arrival)

    movable_maintenance: dict[str, list[MachineMaintenance]] = {}
    for window in state.machine_maintenance:
        if window.maintenance_type in _MOVABLE_MAINTENANCE:
            movable_maintenance.setdefault(window.machine_id, []).append(window)

    return RecommendationContext(
        state=state,
        schedule=schedule,
        risk_report=risk_report,
        machines_by_work_center=machines_by_wc,
        machine_work_center=machine_work_center,
        machine_busy_minutes=machine_busy,
        skill_to_workers=skill_to_workers,
        order_by_id={o.order_id: o for o in state.production_orders},
        inbound_pos_by_product=inbound_pos,
        suppliers_by_product=suppliers_by_product,
        all_supplier_ids={s.supplier_id for s in state.suppliers},
        movable_maintenance_by_machine=movable_maintenance,
    )


@dataclass
class _PendingRecommendation:
    action: RecommendationAction
    addresses_risk_ids: set[str]
    title: str
    description: str
    target_entities: dict[str, list[str]]
    expected_impact: dict[str, Any]
    feasibility: RecommendationFeasibility
    priority: int


class RecommendationBuilder:
    """Accumulates and deduplicates recommendations for a production day."""

    def __init__(self, business_date: str) -> None:
        self._business_date = business_date
        self._pending: dict[tuple, _PendingRecommendation] = {}

    @staticmethod
    def _key(action: RecommendationAction, targets: dict[str, list[str]]) -> tuple:
        normalised = tuple(sorted((k, tuple(sorted(v))) for k, v in targets.items()))
        return (action, normalised)

    def add(
        self,
        *,
        action: RecommendationAction,
        addresses_risk_ids: list[str],
        title: str,
        description: str,
        target_entities: dict[str, list[str]],
        expected_impact: dict[str, Any] | None = None,
        feasibility: RecommendationFeasibility = RecommendationFeasibility.FEASIBLE,
        priority: int = 5,
    ) -> None:
        """Record a recommendation, merging duplicates targeting the same entities."""
        key = self._key(action, target_entities)
        existing = self._pending.get(key)
        if existing is not None:
            existing.addresses_risk_ids.update(addresses_risk_ids)
            existing.priority = max(existing.priority, priority)
            return
        self._pending[key] = _PendingRecommendation(
            action=action,
            addresses_risk_ids=set(addresses_risk_ids),
            title=title,
            description=description,
            target_entities=target_entities,
            expected_impact=expected_impact or {},
            feasibility=feasibility,
            priority=priority,
        )

    def build(self) -> RecommendationSet:
        """Assemble the immutable, priority-sorted :class:`RecommendationSet`."""
        ordered = sorted(
            self._pending.values(), key=lambda r: (-r.priority, r.action.value)
        )
        recommendations: list[Recommendation] = []
        for index, pending in enumerate(ordered, start=1):
            recommendations.append(
                Recommendation(
                    recommendation_id=f"REC-{self._business_date}-{index:04d}",
                    action=pending.action,
                    addresses_risk_ids=sorted(pending.addresses_risk_ids),
                    title=pending.title,
                    description=pending.description,
                    target_entities=pending.target_entities,
                    expected_impact=pending.expected_impact,
                    feasibility=pending.feasibility,
                    priority=pending.priority,
                )
            )
        return RecommendationSet(
            business_date=self._business_date, recommendations=recommendations
        )
