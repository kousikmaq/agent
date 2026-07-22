"""Phase 11 tests: the explanation context builder.

Constructs the deterministic-output DTOs directly (no solver needed) to verify
context assembly, curation/trimming, persistence round-trip, and determinism.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.domain.enums import (
    RecommendationAction,
    RecommendationFeasibility,
    RiskSeverity,
    RiskType,
    ScenarioType,
    SolverStatus,
)
from app.domain.models.analytics import KpiSet
from app.domain.models.change_log import ChangeEvent, ChangeLog
from app.domain.enums import ChangeEventType
from app.domain.models.explanation import ExplanationContext
from app.domain.models.recommendation import Recommendation, RecommendationSet
from app.domain.models.risk import Risk, RiskReport
from app.domain.models.scenario import ScenarioComparison, ScenarioResult
from app.domain.models.schedule import ScheduledOperation, ScheduleResult
from app.explanation import ExplanationContextBuilder

DATE = "2026-07-17"


def _schedule() -> ScheduleResult:
    return ScheduleResult(
        business_date=DATE,
        status=SolverStatus.OPTIMAL,
        scheduled_operations=[
            ScheduledOperation(
                order_id="ORD-1", operation_id="OP-1", machine_id="M-1",
                worker_id="W-1",
                start=datetime(2026, 7, 17, 6, 0), end=datetime(2026, 7, 17, 7, 0),
            ),
            ScheduledOperation(
                order_id="ORD-1", operation_id="OP-2", machine_id="M-2",
                worker_id="W-2",
                start=datetime(2026, 7, 17, 7, 0), end=datetime(2026, 7, 17, 8, 0),
            ),
        ],
        makespan_minutes=120,
        objective_value=120.0,
        solve_time_seconds=0.01,
    )


def _kpis() -> KpiSet:
    return KpiSet(
        business_date=DATE,
        on_time_delivery_rate=1.0,
        average_machine_utilization=0.5,
        total_tardiness_minutes=0,
        work_in_progress=0,
        metrics={"makespan_minutes": 120.0, "scheduled_orders": 1.0},
    )


def _risk(risk_id: str, severity: RiskSeverity, risk_type=RiskType.DELAYED_ORDER) -> Risk:
    return Risk(
        risk_id=risk_id, risk_type=risk_type, severity=severity,
        title=f"{severity} risk", description="d",
    )


def _risks() -> RiskReport:
    return RiskReport(
        business_date=DATE,
        risks=[
            _risk("R-LOW", RiskSeverity.LOW),
            _risk("R-CRIT", RiskSeverity.CRITICAL),
            _risk("R-HIGH", RiskSeverity.HIGH),
        ],
    )


def _rec(rec_id: str, priority: int, action=RecommendationAction.SPLIT_BATCH) -> Recommendation:
    return Recommendation(
        recommendation_id=rec_id, action=action, addresses_risk_ids=["R-CRIT"],
        title=f"rec {rec_id}", description="d",
        feasibility=RecommendationFeasibility.FEASIBLE, priority=priority,
    )


def _recommendations() -> RecommendationSet:
    # Already priority-sorted (engine guarantees this).
    return RecommendationSet(
        business_date=DATE,
        recommendations=[_rec("REC-1", 10), _rec("REC-2", 5)],
    )


def _scenarios() -> ScenarioComparison:
    return ScenarioComparison(
        business_date=DATE,
        baseline_type=ScenarioType.CURRENT_PLAN,
        results=[
            ScenarioResult(scenario_type=ScenarioType.CURRENT_PLAN, name="Current Plan",
                           kpis={"makespan_minutes": 100.0}, is_baseline=True),
            ScenarioResult(scenario_type=ScenarioType.ADDITIONAL_SHIFT, name="Additional Shift",
                           kpis={"makespan_minutes": 50.0}, is_baseline=False),
        ],
        kpi_deltas={"Additional Shift": {"makespan_minutes": -50.0}},
    )


def _change_log() -> ChangeLog:
    return ChangeLog(
        business_date=DATE, previous_date="2026-07-16",
        events=[
            ChangeEvent(event_id="CHG-1", event_type=ChangeEventType.NEW_PRODUCTION_ORDER,
                        entity_type="production_order", entity_id="ORD-9", description="d"),
        ],
    )


def _context(builder: ExplanationContextBuilder, with_changes: bool = True) -> ExplanationContext:
    return builder.build(
        business_date=DATE,
        schedule=_schedule(),
        kpis=_kpis(),
        risks=_risks(),
        recommendations=_recommendations(),
        scenario_comparison=_scenarios(),
        change_log=_change_log() if with_changes else None,
    )


def test_build_returns_full_context() -> None:
    context = _context(ExplanationContextBuilder())
    assert isinstance(context, ExplanationContext)
    assert context.business_date == DATE
    assert len(context.schedule.scheduled_operations) == 2
    assert context.change_log is not None


def test_summary_trims_schedule_to_counts() -> None:
    context = _context(ExplanationContextBuilder())
    summary = ExplanationContextBuilder().summarize(context)
    assert summary.schedule.scheduled_operations == 2
    assert summary.schedule.scheduled_orders == 1
    assert summary.schedule.makespan_minutes == 120


def test_summary_ranks_and_limits_top_risks() -> None:
    builder = ExplanationContextBuilder(top_risks=2)
    summary = builder.summarize(_context(builder))
    assert summary.risks.total == 3
    assert summary.risks.by_severity == {"LOW": 1, "CRITICAL": 1, "HIGH": 1}
    # Top-2 by severity: CRITICAL then HIGH.
    assert [r.risk_id for r in summary.risks.top] == ["R-CRIT", "R-HIGH"]


def test_summary_limits_top_recommendations() -> None:
    builder = ExplanationContextBuilder(top_recommendations=1)
    summary = builder.summarize(_context(builder))
    assert summary.recommendations.total == 2
    assert len(summary.recommendations.top) == 1
    assert summary.recommendations.top[0].recommendation_id == "REC-1"


def test_summary_identifies_best_makespan_scenario() -> None:
    builder = ExplanationContextBuilder()
    summary = builder.summarize(_context(builder))
    assert summary.scenarios.best_makespan_scenario == "Additional Shift"
    assert summary.scenarios.baseline_type == "CURRENT_PLAN"


def test_change_summary_present_and_absent() -> None:
    builder = ExplanationContextBuilder()
    with_changes = builder.summarize(_context(builder, with_changes=True))
    assert with_changes.changes is not None
    assert with_changes.changes.total == 1
    assert with_changes.changes.previous_date == "2026-07-16"

    without = builder.summarize(_context(builder, with_changes=False))
    assert without.changes is None


def test_persist_round_trips_context(tmp_path: Path) -> None:
    builder = ExplanationContextBuilder()
    context = _context(builder)
    summary = builder.summarize(context)

    directory = builder.persist(context, summary, tmp_path)
    assert (directory / "explanation_context.json").exists()
    assert (directory / "explanation_summary.json").exists()

    reloaded = ExplanationContext.model_validate_json(
        (directory / "explanation_context.json").read_text(encoding="utf-8")
    )
    assert reloaded.model_dump(mode="json") == context.model_dump(mode="json")


def test_summary_is_deterministic() -> None:
    builder = ExplanationContextBuilder()
    context = _context(builder)
    a = builder.summarize(context)
    b = builder.summarize(context)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
