"""Explanation Context Builder.

Merges the deterministic outputs of Optimization, Analytics, Risk Detection,
Recommendation, and Scenario Planning (plus the day's change log) into:

* the full :class:`ExplanationContext` (persisted per day for audit), and
* a curated, token-bounded :class:`ExplanationSummary` (handed to the LLM).

This is the *only* seam that feeds the chat/LLM layer - by construction the LLM
cannot reach the solver or mutate any decision.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.core.logging import get_logger
from app.domain.models.analytics import KpiSet
from app.domain.models.change_log import ChangeLog
from app.domain.models.explanation import ExplanationContext
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import RiskReport
from app.domain.models.scenario import ScenarioComparison
from app.domain.models.schedule import ScheduleResult
from app.explanation.schema import (
    ChangeSummary,
    ExplanationSummary,
    LateOrderDigest,
    MachineLoadDigest,
    RecommendationDigest,
    RecommendationSummary,
    RiskDigest,
    RiskSummary,
    ScenarioDigest,
    ScenarioSummary,
    ScheduleSummary,
)
from app.utils.file_utils import ensure_dir

logger = get_logger(__name__)

# Deterministic severity ordering for ranking risks.
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

CONTEXT_FILENAME = "explanation_context.json"
SUMMARY_FILENAME = "explanation_summary.json"


class ExplanationContextBuilder:
    """Assembles the audit context and the curated LLM summary."""

    def __init__(self, top_risks: int = 10, top_recommendations: int = 10) -> None:
        self._top_risks = top_risks
        self._top_recommendations = top_recommendations

    # -- Full context (audit) ----------------------------------------------
    def build(
        self,
        *,
        business_date: str,
        schedule: ScheduleResult,
        kpis: KpiSet,
        risks: RiskReport,
        recommendations: RecommendationSet,
        scenario_comparison: ScenarioComparison,
        change_log: ChangeLog | None = None,
    ) -> ExplanationContext:
        """Merge all deterministic outputs into the full explanation context."""
        return ExplanationContext(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
            change_log=change_log,
        )

    # -- Curated summary (LLM) ----------------------------------------------
    def summarize(self, context: ExplanationContext) -> ExplanationSummary:
        """Produce the trimmed, token-bounded summary for the LLM."""
        return ExplanationSummary(
            business_date=context.business_date,
            schedule=self._schedule_summary(context.schedule),
            kpis=context.kpis.model_dump(mode="json"),
            risks=self._risk_summary(context.risks),
            recommendations=self._recommendation_summary(context.recommendations),
            scenarios=self._scenario_summary(context.scenario_comparison),
            changes=self._change_summary(context.change_log),
            late_orders=self._late_orders(context.schedule, context.risks),
            machine_load=self._machine_load(context.schedule),
        )

    # -- Persistence --------------------------------------------------------
    def persist(
        self,
        context: ExplanationContext,
        summary: ExplanationSummary,
        outputs_dir: Path,
    ) -> Path:
        """Write the context and summary JSON under ``outputs/<business_date>/``.

        Returns the directory written to. The persisted context is the exact
        object the assistant is grounded on, giving full auditability.
        """
        directory = ensure_dir(outputs_dir / context.business_date)
        (directory / CONTEXT_FILENAME).write_text(
            context.model_dump_json(indent=2), encoding="utf-8"
        )
        (directory / SUMMARY_FILENAME).write_text(
            summary.model_dump_json(indent=2), encoding="utf-8"
        )
        logger.info("Persisted explanation context for %s to %s", context.business_date, directory)
        return directory

    # -- Internal builders --------------------------------------------------
    @staticmethod
    def _schedule_summary(schedule: ScheduleResult) -> ScheduleSummary:
        order_ids = {op.order_id for op in schedule.scheduled_operations}
        return ScheduleSummary(
            status=str(schedule.status),
            scheduled_operations=len(schedule.scheduled_operations),
            scheduled_orders=len(order_ids),
            makespan_minutes=schedule.makespan_minutes,
            objective_value=schedule.objective_value,
            solve_time_seconds=schedule.solve_time_seconds,
        )

    def _risk_summary(self, risks: RiskReport) -> RiskSummary:
        by_severity = Counter(str(r.severity) for r in risks.risks)
        by_type = Counter(str(r.risk_type) for r in risks.risks)
        ranked = sorted(
            risks.risks,
            key=lambda r: (_SEVERITY_ORDER.get(str(r.severity), 99), r.risk_id),
        )
        top = [
            RiskDigest(
                risk_id=r.risk_id,
                risk_type=str(r.risk_type),
                severity=str(r.severity),
                title=r.title,
                description=r.description,
                affected_entities=dict(r.affected_entities),
                evidence=dict(r.evidence),
            )
            for r in ranked[: self._top_risks]
        ]
        return RiskSummary(
            total=len(risks.risks),
            by_severity=dict(by_severity),
            by_type=dict(by_type),
            top=top,
        )

    @staticmethod
    def _late_orders(
        schedule: ScheduleResult, risks: RiskReport, limit: int = 12
    ) -> list[LateOrderDigest]:
        """Late orders with their route (machines) and the risks causing delay."""
        # Machines used by each order, in scheduled order.
        machines_by_order: dict[str, list[str]] = {}
        for op in schedule.scheduled_operations:
            machines = machines_by_order.setdefault(op.order_id, [])
            if op.machine_id not in machines:
                machines.append(op.machine_id)

        # Non-delay risks that name specific orders explain the cause.
        causes_by_order: dict[str, list[str]] = {}
        for r in risks.risks:
            if str(r.risk_type) == "DELAYED_ORDER":
                continue
            for oid in r.affected_entities.get("order_ids", []):
                causes_by_order.setdefault(oid, []).append(r.title)

        digests: list[LateOrderDigest] = []
        for r in risks.risks:
            if str(r.risk_type) != "DELAYED_ORDER":
                continue
            order_ids = r.affected_entities.get("order_ids", [])
            oid = order_ids[0] if order_ids else None
            if oid is None:
                continue
            ev = r.evidence or {}
            digests.append(
                LateOrderDigest(
                    order_id=oid,
                    tardiness_minutes=float(ev.get("tardiness_minutes", 0.0)),
                    due_date=str(ev["due_date"]) if ev.get("due_date") else None,
                    scheduled_completion=(
                        str(ev["completion"]) if ev.get("completion") else None
                    ),
                    machines=machines_by_order.get(oid, []),
                    causes=causes_by_order.get(oid, []),
                )
            )
        digests.sort(key=lambda d: d.tardiness_minutes, reverse=True)
        return digests[:limit]

    @staticmethod
    def _machine_load(
        schedule: ScheduleResult, limit: int = 15
    ) -> list[MachineLoadDigest]:
        """Per-machine scheduled minutes and op count for the day, busiest first."""
        minutes: dict[str, float] = {}
        ops: dict[str, int] = {}
        for op in schedule.scheduled_operations:
            dur = (op.end - op.start).total_seconds() / 60.0
            minutes[op.machine_id] = minutes.get(op.machine_id, 0.0) + dur
            ops[op.machine_id] = ops.get(op.machine_id, 0) + 1
        digests = [
            MachineLoadDigest(
                machine_id=mid,
                scheduled_minutes=round(mins),
                operations=ops[mid],
            )
            for mid, mins in minutes.items()
        ]
        digests.sort(key=lambda d: d.scheduled_minutes, reverse=True)
        return digests[:limit]

    def _recommendation_summary(
        self, recommendations: RecommendationSet
    ) -> RecommendationSummary:
        by_action = Counter(str(r.action) for r in recommendations.recommendations)
        by_feasibility = Counter(
            str(r.feasibility) for r in recommendations.recommendations
        )
        # Recommendations arrive already priority-sorted from the engine.
        top = [
            RecommendationDigest(
                recommendation_id=r.recommendation_id,
                action=str(r.action),
                priority=r.priority,
                feasibility=str(r.feasibility),
                title=r.title,
                addresses_risk_ids=list(r.addresses_risk_ids),
            )
            for r in recommendations.recommendations[: self._top_recommendations]
        ]
        return RecommendationSummary(
            total=len(recommendations.recommendations),
            by_action=dict(by_action),
            by_feasibility=dict(by_feasibility),
            top=top,
        )

    @staticmethod
    def _scenario_summary(comparison: ScenarioComparison) -> ScenarioSummary:
        digests = [
            ScenarioDigest(
                scenario_type=str(result.scenario_type),
                name=result.name,
                is_baseline=result.is_baseline,
                kpis=dict(result.kpis),
            )
            for result in comparison.results
        ]
        best = None
        candidates = [
            r for r in comparison.results if "makespan_minutes" in r.kpis
        ]
        if candidates:
            best = min(candidates, key=lambda r: r.kpis["makespan_minutes"]).name
        return ScenarioSummary(
            baseline_type=str(comparison.baseline_type),
            scenarios=digests,
            kpi_deltas=comparison.kpi_deltas,
            best_makespan_scenario=best,
        )

    @staticmethod
    def _change_summary(change_log: ChangeLog | None) -> ChangeSummary | None:
        if change_log is None:
            return None
        by_type = Counter(str(e.event_type) for e in change_log.events)
        return ChangeSummary(
            total=len(change_log.events),
            by_type=dict(by_type),
            previous_date=change_log.previous_date,
        )
