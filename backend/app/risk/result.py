"""Risk detection context and report builder.

Shared, precomputed context passed to every detector (so each avoids
recomputing schedule aggregates), plus a small builder that assigns stable ids
and assembles the immutable :class:`RiskReport`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.analytics.kpis import (
    MachineUsage,
    OrderOutcome,
    ScheduleAggregates,
    aggregate_schedule,
)
from app.domain.enums import RiskSeverity, RiskType
from app.domain.models.analytics import KpiSet
from app.domain.models.factory_state import FactoryState
from app.domain.models.risk import Risk, RiskReport
from app.domain.models.routing import Operation
from app.domain.models.schedule import ScheduledOperation, ScheduleResult


def operation_duration(operation: Operation, quantity: int) -> int:
    """Deterministic processing time (minutes) - mirrors the optimizer model."""
    return max(1, operation.setup_minutes + math.ceil(operation.run_minutes_per_unit * quantity))


@dataclass
class RiskContext:
    """Everything a detector needs, precomputed once."""

    state: FactoryState
    schedule: ScheduleResult
    kpis: KpiSet
    aggregates: ScheduleAggregates
    machine_usage_by_id: dict[str, MachineUsage] = field(default_factory=dict)
    order_outcome_by_id: dict[str, OrderOutcome] = field(default_factory=dict)
    ops_by_machine: dict[str, list[ScheduledOperation]] = field(default_factory=dict)
    ops_by_worker: dict[str, list[ScheduledOperation]] = field(default_factory=dict)
    operation_by_id: dict[str, Operation] = field(default_factory=dict)
    machine_work_center: dict[str, str] = field(default_factory=dict)


def build_risk_context(
    state: FactoryState, schedule: ScheduleResult, kpis: KpiSet
) -> RiskContext:
    """Assemble the :class:`RiskContext` from inputs (computed deterministically)."""
    aggregates = aggregate_schedule(state, schedule)

    ops_by_machine: dict[str, list[ScheduledOperation]] = {}
    ops_by_worker: dict[str, list[ScheduledOperation]] = {}
    for op in schedule.scheduled_operations:
        ops_by_machine.setdefault(op.machine_id, []).append(op)
        if op.worker_id:
            ops_by_worker.setdefault(op.worker_id, []).append(op)

    operation_by_id: dict[str, Operation] = {}
    for routing in state.routings:
        for operation in routing.operations:
            operation_by_id[operation.operation_id] = operation

    return RiskContext(
        state=state,
        schedule=schedule,
        kpis=kpis,
        aggregates=aggregates,
        machine_usage_by_id={m.machine_id: m for m in aggregates.machine_usage},
        order_outcome_by_id={o.order_id: o for o in aggregates.order_outcomes},
        ops_by_machine=ops_by_machine,
        ops_by_worker=ops_by_worker,
        operation_by_id=operation_by_id,
        machine_work_center={m.machine_id: m.work_center for m in state.machines},
    )


class RiskBuilder:
    """Accumulates detected risks and assigns deterministic ids."""

    def __init__(self, business_date: str) -> None:
        self._business_date = business_date
        self._risks: list[Risk] = []

    def add(
        self,
        *,
        risk_type: RiskType,
        severity: RiskSeverity,
        title: str,
        description: str,
        affected_entities: dict[str, list[str]] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Record a single detected risk."""
        risk_id = f"RISK-{self._business_date}-{len(self._risks) + 1:04d}"
        self._risks.append(
            Risk(
                risk_id=risk_id,
                risk_type=risk_type,
                severity=severity,
                title=title,
                description=description,
                affected_entities=affected_entities or {},
                evidence=evidence or {},
            )
        )

    def build(self) -> RiskReport:
        """Assemble the immutable :class:`RiskReport`."""
        return RiskReport(business_date=self._business_date, risks=list(self._risks))
