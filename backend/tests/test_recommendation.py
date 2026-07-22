"""Phase 9 tests: the recommendation engine.

Each test builds a minimal state + targeted risk report and asserts the correct
recommendation action (and feasibility) is produced.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.domain.enums import (
    MaintenanceType,
    OrderStatus,
    PurchaseOrderStatus,
    RecommendationAction,
    RecommendationFeasibility,
    RiskSeverity,
    RiskType,
    SolverStatus,
)
from datetime import datetime, time
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import Machine, MachineMaintenance
from app.domain.models.production_order import ProductionOrder
from app.domain.models.purchase_order import PurchaseOrder
from app.domain.models.risk import Risk, RiskReport
from app.domain.models.schedule import ScheduleResult
from app.domain.models.supplier import Supplier
from app.domain.models.workforce import Worker, WorkerSkill
from app.recommendation import RecommendationEngine

BIZ = date(2026, 7, 17)


def _risk(risk_type: RiskType, *, severity=RiskSeverity.HIGH, affected=None, evidence=None) -> Risk:
    return Risk(
        risk_id=f"RISK-{risk_type.value}",
        risk_type=risk_type,
        severity=severity,
        title="t",
        description="d",
        affected_entities=affected or {},
        evidence=evidence or {},
    )


def _report(*risks: Risk) -> RiskReport:
    return RiskReport(business_date="2026-07-17", risks=list(risks))


def _empty_schedule() -> ScheduleResult:
    return ScheduleResult(
        business_date="2026-07-17", status=SolverStatus.OPTIMAL, scheduled_operations=[]
    )


def _recommend(state: FactoryState, report: RiskReport):
    return RecommendationEngine().recommend(state, _empty_schedule(), report)


def _actions(result) -> set:
    return {r.action for r in result.recommendations}


def test_machine_overload_suggests_alternate_machine() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        machines=[
            Machine(machine_id="M-1", name="A", work_center="WC"),
            Machine(machine_id="M-2", name="B", work_center="WC"),
        ],
    )
    report = _report(_risk(RiskType.MACHINE_OVERLOAD, affected={"machine_ids": ["M-1"]}))
    result = _recommend(state, report)
    assert RecommendationAction.ASSIGN_ALTERNATE_MACHINE in _actions(result)


def test_no_alternate_machine_when_alone_in_work_center() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        machines=[Machine(machine_id="M-1", name="A", work_center="WC")],
    )
    report = _report(_risk(RiskType.MACHINE_OVERLOAD, affected={"machine_ids": ["M-1"]}))
    result = _recommend(state, report)
    assert RecommendationAction.ASSIGN_ALTERNATE_MACHINE not in _actions(result)


def test_worker_conflict_with_available_worker_is_feasible() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        workers=[Worker(worker_id="W-9", name="Spare")],
        worker_skills=[WorkerSkill(worker_id="W-9", skill="SKILL_WC")],
    )
    report = _report(
        _risk(
            RiskType.WORKER_CONFLICT,
            affected={"operation_ids": ["OP-1"]},
            evidence={"required_skill": "SKILL_WC"},
        )
    )
    result = _recommend(state, report)
    rec = next(r for r in result.recommendations if r.action == RecommendationAction.ASSIGN_ALTERNATE_WORKER)
    assert rec.feasibility is RecommendationFeasibility.FEASIBLE
    assert "W-9" in rec.expected_impact["candidate_workers"]


def test_worker_conflict_without_worker_requires_approval() -> None:
    state = FactoryState(business_date="2026-07-17")
    report = _report(
        _risk(
            RiskType.WORKER_CONFLICT,
            affected={"operation_ids": ["OP-1"]},
            evidence={"required_skill": "SKILL_WC"},
        )
    )
    result = _recommend(state, report)
    rec = next(r for r in result.recommendations if r.action == RecommendationAction.ASSIGN_ALTERNATE_WORKER)
    assert rec.feasibility is RecommendationFeasibility.REQUIRES_APPROVAL


def test_delayed_large_order_suggests_split_batch() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[
            ProductionOrder(
                order_id="ORD-1", product_id="FG-1", quantity=100,
                release_date=BIZ, due_date=BIZ + timedelta(days=5),
                status=OrderStatus.RELEASED,
            )
        ],
    )
    report = _report(_risk(RiskType.DELAYED_ORDER, affected={"order_ids": ["ORD-1"]}))
    result = _recommend(state, report)
    assert RecommendationAction.SPLIT_BATCH in _actions(result)


def test_maintenance_conflict_suggests_reschedule() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        machines=[Machine(machine_id="M-1", name="A", work_center="WC")],
        machine_maintenance=[
            MachineMaintenance(
                maintenance_id="MT-1", machine_id="M-1",
                maintenance_type=MaintenanceType.PREVENTIVE,
                start=datetime.combine(BIZ, time(8, 0)),
                end=datetime.combine(BIZ, time(12, 0)),
            )
        ],
    )
    report = _report(_risk(RiskType.MAINTENANCE_CONFLICT, affected={"machine_ids": ["M-1"]}))
    result = _recommend(state, report)
    assert RecommendationAction.RESCHEDULE_MAINTENANCE in _actions(result)


def test_capacity_shortage_suggests_overtime() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        workers=[Worker(worker_id="W-1", name="A", overtime_allowed=True)],
        worker_skills=[WorkerSkill(worker_id="W-1", skill="SKILL_WC")],
    )
    report = _report(_risk(RiskType.CAPACITY_SHORTAGE, affected={"work_centers": ["WC"]}))
    result = _recommend(state, report)
    assert RecommendationAction.APPROVE_OVERTIME in _actions(result)


def test_material_shortage_with_inbound_po_expedites() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        suppliers=[Supplier(supplier_id="SP-1", name="S")],
        purchase_orders=[
            PurchaseOrder(
                po_id="PO-1", supplier_id="SP-1", product_id="RM-1", quantity=100,
                order_date=BIZ, expected_arrival=BIZ + timedelta(days=3),
                status=PurchaseOrderStatus.IN_TRANSIT,
            )
        ],
    )
    report = _report(_risk(RiskType.MATERIAL_SHORTAGE, affected={"product_ids": ["RM-1"]}))
    result = _recommend(state, report)
    assert RecommendationAction.EXPEDITE_PURCHASE_ORDER in _actions(result)


def test_material_shortage_without_po_replenishes_alternate_supplier() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        suppliers=[Supplier(supplier_id="SP-1", name="S"), Supplier(supplier_id="SP-2", name="T")],
    )
    report = _report(_risk(RiskType.MATERIAL_SHORTAGE, affected={"product_ids": ["RM-1"]}))
    result = _recommend(state, report)
    rec = next(r for r in result.recommendations if r.action == RecommendationAction.REPLENISH_ALTERNATE_SUPPLIER)
    assert rec.feasibility is RecommendationFeasibility.FEASIBLE


def test_duplicate_risks_are_merged() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        machines=[
            Machine(machine_id="M-1", name="A", work_center="WC"),
            Machine(machine_id="M-2", name="B", work_center="WC"),
        ],
    )
    report = _report(
        _risk(RiskType.MACHINE_OVERLOAD, severity=RiskSeverity.HIGH, affected={"machine_ids": ["M-1"]}),
        _risk(RiskType.MAINTENANCE_CONFLICT, severity=RiskSeverity.CRITICAL, affected={"machine_ids": ["M-1"]}),
    )
    result = _recommend(state, report)
    alt = [r for r in result.recommendations if r.action == RecommendationAction.ASSIGN_ALTERNATE_MACHINE]
    assert len(alt) == 1
    assert len(alt[0].addresses_risk_ids) == 2  # both risks merged
    assert alt[0].priority == 10  # max severity wins


def test_empty_risk_report_yields_no_recommendations() -> None:
    result = _recommend(FactoryState(business_date="2026-07-17"), _report())
    assert result.recommendations == []


def test_recommendations_are_deterministic() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        machines=[
            Machine(machine_id="M-1", name="A", work_center="WC"),
            Machine(machine_id="M-2", name="B", work_center="WC"),
        ],
    )
    report = _report(_risk(RiskType.MACHINE_OVERLOAD, affected={"machine_ids": ["M-1"]}))
    a = _recommend(state, report)
    b = _recommend(state, report)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
