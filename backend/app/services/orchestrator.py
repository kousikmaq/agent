"""Planning orchestration and results persistence.

Coordinates the full deterministic daily pipeline
(load -> validate -> rules -> solve -> analytics -> risk -> recommendation ->
scenario -> explanation) and persists every artifact under
``outputs/<business_date>/``. The API layer runs the pipeline through
:class:`PlanningOrchestrator` and serves cached artifacts via
:class:`ResultsStore`, so expensive solves are not repeated on every request.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.analytics import AnalyticsEngine
from app.analytics.materials import build_materials_report
from app.core.logging import get_logger
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.enums import RecommendationAction, ScenarioType
from app.domain.models.analytics import KpiSet
from app.domain.models.explanation import ExplanationContext
from app.domain.models.modifications import PlanModification, PlanModifications
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import RiskReport
from app.domain.models.scenario import ScenarioComparison, ScenarioResult
from app.domain.models.schedule import ScheduleResult
from app.explanation import ExplanationContextBuilder
from app.explanation.schema import ExplanationSummary
from app.ingestion import CsvDataSource, FactoryStateLoader
from app.optimization import SchedulingSolver, SolverOptions
from app.optimization.objective_spec import weights_for
from app.recommendation import RecommendationEngine
from app.risk import RiskDetectionEngine
from app.rules import BusinessRulesEngine
from app.scenario import ScenarioPlanningEngine
from app.scenario.comparison import compute_kpi_deltas, extract_scenario_kpis
from app.scenario.definitions import DEFAULT_SCENARIOS
from app.services.fixes import apply_fix
from app.utils.file_utils import ensure_dir

logger = get_logger(__name__)


class PlanningResult(BaseModel):
    """The bundle of deterministic outputs for one production day."""

    business_date: str
    schedule: ScheduleResult
    kpis: KpiSet
    risks: RiskReport
    recommendations: RecommendationSet
    scenario_comparison: ScenarioComparison


class ResultsStore:
    """Reads and writes persisted planning artifacts under ``outputs/<date>/``."""

    SCHEDULE = "schedule.json"
    KPIS = "kpis.json"
    RISKS = "risks.json"
    RECOMMENDATIONS = "recommendations.json"
    SCENARIOS = "scenarios.json"
    CONTEXT = "explanation_context.json"
    SUMMARY = "explanation_summary.json"
    MODIFICATIONS = "modifications.json"
    ORIGINAL_KPIS = "original_plan.json"
    PURCHASE_ORDERS = "purchase_orders.json"

    def __init__(self, outputs_dir: Path) -> None:
        self._outputs_dir = ensure_dir(outputs_dir)

    def _dir(self, business_date: str) -> Path:
        return self._outputs_dir / business_date

    def exists(self, business_date: str) -> bool:
        """Whether a full result set has been persisted for a date."""
        return (self._dir(business_date) / self.SCHEDULE).exists()

    def save(
        self,
        result: PlanningResult,
        context: ExplanationContext,
        summary: ExplanationSummary,
    ) -> Path:
        """Persist every artifact for a production day; return the directory."""
        directory = ensure_dir(self._dir(result.business_date))
        _write(directory / self.SCHEDULE, result.schedule)
        _write(directory / self.KPIS, result.kpis)
        _write(directory / self.RISKS, result.risks)
        _write(directory / self.RECOMMENDATIONS, result.recommendations)
        _write(directory / self.SCENARIOS, result.scenario_comparison)
        _write(directory / self.CONTEXT, context)
        _write(directory / self.SUMMARY, summary)
        return directory

    # --- Typed loaders (return None when absent) ---------------------------
    def load_schedule(self, business_date: str) -> ScheduleResult | None:
        return _read(self._dir(business_date) / self.SCHEDULE, ScheduleResult)

    def load_kpis(self, business_date: str) -> KpiSet | None:
        return _read(self._dir(business_date) / self.KPIS, KpiSet)

    def load_risks(self, business_date: str) -> RiskReport | None:
        return _read(self._dir(business_date) / self.RISKS, RiskReport)

    def load_recommendations(self, business_date: str) -> RecommendationSet | None:
        return _read(self._dir(business_date) / self.RECOMMENDATIONS, RecommendationSet)

    def load_scenarios(self, business_date: str) -> ScenarioComparison | None:
        return _read(self._dir(business_date) / self.SCENARIOS, ScenarioComparison)

    def load_context(self, business_date: str) -> ExplanationContext | None:
        return _read(self._dir(business_date) / self.CONTEXT, ExplanationContext)

    def load_summary(self, business_date: str) -> ExplanationSummary | None:
        return _read(self._dir(business_date) / self.SUMMARY, ExplanationSummary)

    def save_modifications(self, mods: PlanModifications) -> None:
        directory = ensure_dir(self._dir(mods.business_date))
        _write(directory / self.MODIFICATIONS, mods)

    def load_modifications(self, business_date: str) -> PlanModifications | None:
        return _read(self._dir(business_date) / self.MODIFICATIONS, PlanModifications)

    # --- Original (baseline) plan KPIs ------------------------------------
    # A write-once snapshot of the day's ORIGINAL plan KPIs, captured the first
    # time the pipeline runs for the date. It is deliberately never overwritten
    # by applying scenarios, mitigating risks, removing modifications or even a
    # later re-run, so the Live Operations page can pin the original plan.
    def save_original_kpis(
        self, business_date: str, kpis: dict[str, float]
    ) -> None:
        directory = ensure_dir(self._dir(business_date))
        path = directory / self.ORIGINAL_KPIS
        if path.exists():
            return  # write-once: keep the first captured original plan.
        path.write_text(json.dumps(kpis, indent=2), encoding="utf-8")

    def load_original_kpis(self, business_date: str) -> dict[str, float] | None:
        path = self._dir(business_date) / self.ORIGINAL_KPIS
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # --- Purchase orders (material replenishment) -------------------------
    # Per-day log of purchase orders placed (auto or manual) so the Materials
    # tab can show what was ordered and when, and so the autonomous reorder can
    # de-duplicate (place at most one auto order per material per day).
    def load_purchase_orders(self, business_date: str) -> list[dict]:
        path = self._dir(business_date) / self.PURCHASE_ORDERS
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def append_purchase_order(self, business_date: str, po: dict) -> None:
        directory = ensure_dir(self._dir(business_date))
        orders = self.load_purchase_orders(business_date)
        orders.append(po)
        (directory / self.PURCHASE_ORDERS).write_text(
            json.dumps(orders, indent=2), encoding="utf-8"
        )

    # --- Per-scenario schedules -------------------------------------------
    # Each what-if scenario's full schedule is persisted at morning-run time so
    # selecting a scenario can reuse the exact plan it previewed instead of
    # re-solving (which would drift and recompute needlessly).
    def save_scenario_schedule(
        self, business_date: str, scenario_type: ScenarioType, schedule: ScheduleResult
    ) -> None:
        directory = ensure_dir(self._dir(business_date))
        _write(directory / f"scenario_{scenario_type.value}.json", schedule)

    def load_scenario_schedule(
        self, business_date: str, scenario_type: ScenarioType
    ) -> ScheduleResult | None:
        return _read(
            self._dir(business_date) / f"scenario_{scenario_type.value}.json",
            ScheduleResult,
        )


def _write(path: Path, model: BaseModel) -> None:
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _read(path: Path, model_cls: type[BaseModel]):
    if not path.exists():
        return None
    return model_cls.model_validate_json(path.read_text(encoding="utf-8"))


def _light_comparison(business_date: str, kpis: KpiSet) -> ScenarioComparison:
    """A single-entry scenario comparison for the applied plan.

    Used by mitigation re-plans to avoid re-solving all four what-if scenarios
    (which would multiply solve time); the full comparison is rebuilt on the
    next complete pipeline run.
    """
    applied = ScenarioResult(
        scenario_type=ScenarioType.CURRENT_PLAN,
        name="Applied plan",
        kpis=extract_scenario_kpis(kpis),
        is_baseline=True,
    )
    return ScenarioComparison(
        business_date=business_date,
        baseline_type=ScenarioType.CURRENT_PLAN,
        results=[applied],
        kpi_deltas={},
    )


def _comparison_with_applied(
    existing: ScenarioComparison,
    applied_type: ScenarioType,
    kpis: KpiSet,
) -> ScenarioComparison:
    """Return ``existing`` with only the applied scenario's row refreshed.

    Committing a scenario must not silently re-solve (and move) the other
    what-if plans. We therefore keep every other row exactly as it was and only
    update the applied scenario's KPIs to the freshly committed values, then
    recompute the deltas against the (unchanged) baseline row.
    """
    applied_kpis = extract_scenario_kpis(kpis)
    results = [
        result.model_copy(update={"kpis": applied_kpis})
        if result.scenario_type == applied_type
        else result
        for result in existing.results
    ]
    baseline = next(
        (r for r in results if r.scenario_type == existing.baseline_type),
        results[0] if results else None,
    )
    deltas = compute_kpi_deltas(baseline, results) if baseline else {}
    return ScenarioComparison(
        business_date=existing.business_date,
        baseline_type=existing.baseline_type,
        committed_type=applied_type,
        results=results,
        kpi_deltas=deltas,
    )


# Readable labels for the modification log shown in the "Current Plan" tab.
_ACTION_LABELS: dict[str, str] = {
    "RAISE_PRIORITY": "Raised order priority",
    "ASSIGN_ALTERNATE_MACHINE": "Used alternate machines",
    "ADD_SHIFT": "Added a shift",
    "APPROVE_OVERTIME": "Enabled overtime",
    "RESCHEDULE_MAINTENANCE": "Rescheduled maintenance",
    "ASSIGN_ALTERNATE_WORKER": "Reassigned workers",
    "EXPEDITE_PURCHASE_ORDER": "Expedited purchase order",
    "REPLENISH_ALTERNATE_SUPPLIER": "Replenished material",
    "SPLIT_BATCH": "Split batches",
}


class PlanningOrchestrator:
    """Runs the full deterministic planning pipeline for a business date."""

    def __init__(
        self,
        datasets_dir: Path,
        outputs_dir: Path,
        options: SolverOptions | None = None,
    ) -> None:
        self._datasets_dir = datasets_dir
        self._loader = FactoryStateLoader(CsvDataSource(datasets_dir))
        self._store = ResultsStore(outputs_dir)
        self._default_options = options or SolverOptions.from_settings()

        self._rules = BusinessRulesEngine()
        self._analytics = AnalyticsEngine()
        self._risk = RiskDetectionEngine()
        self._recommendation = RecommendationEngine()
        self._explanation = ExplanationContextBuilder()

    @property
    def store(self) -> ResultsStore:
        """The results store used for persistence and retrieval."""
        return self._store

    def available_dates(self) -> list[str]:
        """Business dates available from the data source."""
        return self._loader.available_dates()

    def run(
        self, business_date: str, options: SolverOptions | None = None
    ) -> PlanningResult:
        """Execute the full pipeline for ``business_date`` and persist results."""
        options = options or self._default_options
        logger.info("Running planning pipeline for %s.", business_date)

        state = self._loader.load(business_date)
        policy = self._rules.evaluate(state)

        schedule = SchedulingSolver(options).solve(
            state, policy, weights_for(ScenarioType.CURRENT_PLAN)
        )
        kpis = self._analytics.compute(state, schedule)
        risks = self._risk.detect(state, schedule, kpis)
        recommendations = self._recommendation.recommend(state, schedule, risks)
        scenario_schedules: dict[ScenarioType, ScheduleResult] = {}
        scenario_comparison = ScenarioPlanningEngine(options=options).plan(
            state,
            policy,
            injected={ScenarioType.CURRENT_PLAN: kpis},
            baseline_schedule=schedule,
            schedules_out=scenario_schedules,
        )

        context = self._explanation.build(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
        )
        summary = self._explanation.summarize(context)

        result = PlanningResult(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
        )
        self._store.save(result, context, summary)
        # Persist each scenario's full schedule so selecting a scenario later
        # reuses the exact plan previewed here instead of re-solving.
        for scen_type, scen_schedule in scenario_schedules.items():
            self._store.save_scenario_schedule(business_date, scen_type, scen_schedule)
        # A fresh full run resets the modification log — this plan is the new
        # baseline that later fixes are compared against.
        base = extract_scenario_kpis(kpis)
        # Capture the ORIGINAL plan KPIs once for the day (write-once): the Live
        # Operations page pins these and they must not move when scenarios are
        # applied, risks are mitigated, or the planner re-runs.
        self._store.save_original_kpis(business_date, base)
        self._store.save_modifications(
            PlanModifications(
                business_date=business_date,
                baseline_kpis=base,
                current_kpis=base,
                modifications=[],
            )
        )
        return result

    def _finalize_replan(
        self,
        business_date: str,
        transformed,
        policy,
        options: SolverOptions,
        mod_entries: list[PlanModification],
        replace: bool = False,
    ) -> PlanningResult:
        """Solve a modified state once, persist it, and log the modifications.

        Preserves the existing what-if scenario comparison (so the Scenarios
        tab keeps its three alternatives) instead of re-solving it, and records
        ``mod_entries`` in the day's modification log with the before/after
        KPIs used by the Current Plan tab. When ``replace`` is True the log is
        set to exactly ``mod_entries`` (the caller has already merged with the
        existing entries — used to keep a single consolidated priority entry);
        otherwise ``mod_entries`` is appended.
        """
        prev_mods = self._store.load_modifications(business_date)
        prev_kpis = self._store.load_kpis(business_date)
        existing_scenarios = self._store.load_scenarios(business_date)

        schedule = SchedulingSolver(options).solve(transformed, policy)
        kpis = self._analytics.compute(transformed, schedule)
        risks = self._risk.detect(transformed, schedule, kpis)
        recommendations = self._recommendation.recommend(transformed, schedule, risks)
        scenario_comparison = existing_scenarios or _light_comparison(
            business_date, kpis
        )

        context = self._explanation.build(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
        )
        summary = self._explanation.summarize(context)

        result = PlanningResult(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
        )
        self._store.save(result, context, summary)

        if prev_mods is not None:
            baseline = prev_mods.baseline_kpis
            existing_entries = list(prev_mods.modifications)
        elif prev_kpis is not None:
            baseline = extract_scenario_kpis(prev_kpis)
            existing_entries = []
        else:
            baseline = extract_scenario_kpis(kpis)
            existing_entries = []

        self._store.save_modifications(
            PlanModifications(
                business_date=business_date,
                baseline_kpis=baseline,
                current_kpis=extract_scenario_kpis(kpis),
                modifications=list(mod_entries)
                if replace
                else [*existing_entries, *mod_entries],
            )
        )
        return result

    def apply_scenario(
        self,
        business_date: str,
        scenario_type: ScenarioType,
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Commit a scenario's plan as the current plan for ``business_date``.

        Reuses the scenario's schedule already computed and persisted by the
        morning pipeline run — selecting a plan must NOT re-solve, so the
        committed plan is exactly the one previewed and never drifts. Only the
        downstream artifacts (risks, deliveries, recommendations) are recomputed
        against that fixed schedule. Falls back to solving once if no saved
        scenario schedule exists (e.g. a legacy day).
        """
        options = options or self._default_options
        spec = next(
            (
                s
                for s in DEFAULT_SCENARIOS
                if s.definition.scenario_type == scenario_type
            ),
            None,
        )
        if spec is None:
            raise NotFoundError(
                f"Unknown scenario type: {scenario_type}.",
                details={"scenario_type": str(scenario_type)},
            )

        logger.info(
            "Applying scenario '%s' as the current plan for %s.",
            spec.definition.name,
            business_date,
        )
        state = self._loader.load(business_date)
        policy = self._rules.evaluate(state)
        transformed = spec.transform(
            state.model_copy(deep=True), spec.definition.parameters
        )

        # Reuse the morning-computed scenario schedule if present (no re-solve),
        # so the committed plan matches the preview exactly. The transform is
        # deterministic, so ``transformed`` matches the state that produced the
        # saved schedule and downstream analytics stay consistent.
        saved_schedule = self._store.load_scenario_schedule(
            business_date, scenario_type
        )
        if saved_schedule is not None:
            schedule = saved_schedule
        else:
            schedule = SchedulingSolver(options).solve(
                transformed,
                policy,
                weights_for(scenario_type),
                warm_start=self._store.load_schedule(business_date),
            )
        kpis = self._analytics.compute(transformed, schedule)
        risks = self._risk.detect(transformed, schedule, kpis)
        recommendations = self._recommendation.recommend(transformed, schedule, risks)
        # Preserve the day's EXISTING what-if comparison so committing one plan
        # does not silently re-solve (and therefore move) the other scenarios'
        # numbers — the solver is non-reproducible, so a fresh re-solve of the
        # untouched scenarios would drift. Only the applied scenario's row is
        # refreshed to the committed KPIs so it matches the top bar exactly. If
        # no comparison exists yet, fall back to solving one once.
        existing_scenarios = self._store.load_scenarios(business_date)
        if existing_scenarios is not None:
            scenario_comparison = _comparison_with_applied(
                existing_scenarios, scenario_type, kpis
            )
        else:
            scenario_comparison = ScenarioPlanningEngine(options=options).plan(
                state, policy, injected={scenario_type: kpis}
            ).model_copy(update={"committed_type": scenario_type})

        context = self._explanation.build(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
        )
        summary = self._explanation.summarize(context)

        result = PlanningResult(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
        )
        self._store.save(result, context, summary)
        return result

    def _apply_priority_changes(
        self,
        business_date: str,
        new_levels: dict[str, int],
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Apply priority overrides cumulatively as ONE consolidated modification.

        Merges ``new_levels`` (order_id -> priority 1..10) with any priority
        overrides already in the modification log, rebuilds the plan from the
        day's ORIGINAL state (re-applying any non-priority fixes plus the merged
        priority overrides), solves once, and records a SINGLE priority entry.
        This keeps prioritising several orders — across separate clicks or an
        autonomous run — a single plan and a single log line, never a growing
        list of per-order entries.
        """
        options = options or self._default_options
        state = self._loader.load(business_date)

        target_ids = set(new_levels)
        present = {
            o.order_id for o in state.production_orders if o.order_id in target_ids
        }
        missing = target_ids - present
        if missing:
            raise NotFoundError(
                f"Orders not found for {business_date}: {sorted(missing)}.",
                details={"order_ids": sorted(missing)},
            )

        prev = self._store.load_modifications(business_date)
        existing = list(prev.modifications) if prev is not None else []
        non_priority = [m for m in existing if m.action != "RAISE_PRIORITY"]

        # Cumulative order -> priority map from prior priority entries, then the
        # new overrides (later values win).
        level_map: dict[str, int] = {}
        for m in existing:
            if m.action != "RAISE_PRIORITY":
                continue
            ids = m.targets.get("order_ids", [])
            levels = m.targets.get("priorities") or []
            for i, oid in enumerate(ids):
                level_map[oid] = int(levels[i]) if i < len(levels) else 10
        for oid, level in new_levels.items():
            level_map[oid] = max(1, min(10, int(level)))

        ordered_ids = sorted(level_map)
        transformed = state.model_copy(deep=True)
        for m in non_priority:
            transformed = self._apply_modification(transformed, m)
        transformed.production_orders = [
            o.model_copy(update={"priority": level_map[o.order_id]})
            if o.order_id in level_map
            else o
            for o in transformed.production_orders
        ]
        policy = self._rules.evaluate(transformed)

        logger.info(
            "Prioritising %d order(s) on %s (consolidated) and re-solving.",
            len(ordered_ids),
            business_date,
        )
        entry = PlanModification(
            label="Prioritised "
            + f"{len(ordered_ids)} order(s): "
            + ", ".join(f"{oid}→{level_map[oid]}" for oid in ordered_ids),
            action="RAISE_PRIORITY",
            applied_at=datetime.now().isoformat(timespec="seconds"),
            targets={
                "order_ids": ordered_ids,
                "priorities": [str(level_map[oid]) for oid in ordered_ids],
            },
        )
        entries = [*non_priority, entry]
        return self._finalize_replan(
            business_date, transformed, policy, options, entries, replace=True
        )

    def apply_order_priority(
        self,
        business_date: str,
        order_ids: list[str],
        priority: int = 10,
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Raise the priority of the given orders and re-solve the day.

        Consolidates with any priority overrides already applied so prioritising
        several orders — one by one or in bulk — stays a single re-plan and a
        single modification log entry. Used to mitigate delayed-order risks.
        """
        target = max(1, min(10, priority))
        return self._apply_priority_changes(
            business_date, {oid: target for oid in order_ids}, options
        )

    def auto_remediate(
        self,
        business_date: str,
        priority_max: int = 1,
        notify: bool = False,
        options: SolverOptions | None = None,
    ) -> dict:
        """Autonomously re-plan when top-priority orders are running late.

        Inspects the committed plan and finds orders whose *display* priority is
        at most ``priority_max`` (0 = most urgent) that finish late, raises them
        to top priority and re-plans once — a reversible action recorded in the
        modification log. Optionally emails a risk + replan summary. Returns a
        summary and is a safe no-op when nothing needs doing.
        """
        from app.analytics.kpis import aggregate_schedule

        schedule = self._store.load_schedule(business_date)
        kpis = self._store.load_kpis(business_date)
        if schedule is None or kpis is None:
            return {
                "triggered": False,
                "reason": "no plan for date",
                "critical_orders": [],
            }

        state = self._loader.load(business_date)
        aggregates = aggregate_schedule(state, schedule)
        # Display priority = 10 - raw (0 = most urgent), so display <= max means
        # raw >= (10 - max).
        threshold_raw = 10 - max(0, min(9, priority_max))
        critical = sorted(
            o.order_id
            for o in aggregates.order_outcomes
            if not o.on_time and o.priority >= threshold_raw
        )
        before_otd = kpis.on_time_delivery_rate

        if not critical:
            logger.info(
                "Auto-remediate %s: no top-priority late orders.", business_date
            )
            return {
                "triggered": False,
                "reason": "no high-priority late orders",
                "critical_orders": [],
                "before_otd": before_otd,
            }

        logger.info(
            "Auto-remediate %s: %d high-priority late order(s) %s — re-planning.",
            business_date,
            len(critical),
            critical,
        )
        result = self.apply_order_priority(
            business_date,
            critical,
            priority=10,
            options=options,
        )
        summary = {
            "triggered": True,
            "critical_orders": critical,
            "before_otd": before_otd,
            "after_otd": result.kpis.on_time_delivery_rate,
            "emailed": False,
        }
        if notify:
            summary["emailed"] = self._send_auto_replan_email(business_date, summary)
        return summary

    @staticmethod
    def _send_auto_replan_email(business_date: str, summary: dict) -> bool:
        """Email a risk + replan notification; never raises (returns a flag)."""
        try:
            from app.notifications.email_service import EmailService

            def pct(v: object) -> str:
                return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "n/a"

            orders = ", ".join(summary.get("critical_orders", []))
            n = len(summary.get("critical_orders", []))
            html = (
                f"<h3>Autonomous re-plan applied — {business_date}</h3>"
                f"<p>The agent detected <b>{n}</b> high-priority order(s) running "
                f"late and automatically re-planned to prioritise them.</p>"
                f"<p><b>On-time delivery:</b> {pct(summary.get('before_otd'))} "
                f"&rarr; {pct(summary.get('after_otd'))}</p>"
                f"<p><b>Orders:</b> {orders}</p>"
                f"<p style='color:#888'>This is a reversible action recorded in the "
                f"plan modification log — review it on the Current Plan tab.</p>"
            )
            EmailService().send_html(
                subject=f"[PPO] Autonomous re-plan — {business_date}",
                html_body=html,
            )
            logger.info("Auto-remediate %s: notification email sent.", business_date)
            return True
        except Exception:  # noqa: BLE001 - notifications must never break planning
            logger.exception(
                "Auto-remediate %s: failed to send notification email.", business_date
            )
            return False

    # -- Material replenishment (purchase orders) --------------------------
    @staticmethod
    def _send_po_email(item: str, quantity: int, reason: str) -> str:
        """Email a purchase-order request; returns 'sent' or 'error' (never raises)."""
        try:
            from app.notifications import EmailService, render_purchase_order_email

            subject, html, text = render_purchase_order_email(
                item=item,
                quantity=f"{quantity:,}",
                supplier=None,
                order_id=None,
                needed_by=None,
                reason=reason or None,
            )
            EmailService().send_html(subject, html, text_body=text)
            return "sent"
        except Exception:  # noqa: BLE001 - a failed email must not lose the PO record
            logger.exception("Purchase-order email failed for %s.", item)
            return "error"

    def reorder_material(
        self,
        business_date: str,
        product_id: str,
        quantity: int | None = None,
        reason: str = "",
        mode: str = "manual",
    ) -> dict:
        """Place a purchase order for a material, email it, and log it for the day.

        Returns the recorded purchase order. ``mode`` marks whether it was placed
        by a human ("manual") or the agent ("auto"). Quantity defaults to the
        shortage (rounded up) when not given.
        """
        report = build_materials_report(self._loader.load(business_date))
        line = next((ln for ln in report.lines if ln.product_id == product_id), None)
        if line is None:
            raise NotFoundError(
                f"Material '{product_id}' not found for {business_date}.",
                details={"product_id": product_id},
            )
        if quantity is not None and quantity > 0:
            qty = int(quantity)
        else:
            qty = max(1, int(math.ceil(line.shortage or line.reorder_point or 1)))

        item = f"{product_id} ({line.name})" if line.name else product_id
        email_status = self._send_po_email(item, qty, reason)
        po = {
            "product_id": product_id,
            "name": line.name,
            "quantity": qty,
            "placed_at": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "below_safety": line.below_safety,
            "below_reorder": line.below_reorder,
            "email_status": email_status,
        }
        self._store.append_purchase_order(business_date, po)
        logger.info(
            "Purchase order (%s) placed for %s x%d on %s.",
            mode,
            product_id,
            qty,
            business_date,
        )
        return po

    def auto_reorder(self, business_date: str) -> dict:
        """Autonomously place POs for materials below safety or reorder level.

        De-duplicates against orders already placed for the day (so it runs at
        most once per material per day), and returns a summary. Safe no-op when
        nothing qualifies.
        """
        report = build_materials_report(self._loader.load(business_date))
        already = {po["product_id"] for po in self._store.load_purchase_orders(business_date)}
        placed: list[dict] = []
        skipped: list[str] = []
        for line in report.lines:
            if not (line.below_safety or line.below_reorder):
                continue
            if line.product_id in already:
                skipped.append(line.product_id)
                continue
            reason = (
                "Auto-reorder: below safety stock."
                if line.below_safety
                else "Auto-reorder: below reorder point."
            )
            po = self.reorder_material(
                business_date,
                line.product_id,
                reason=reason,
                mode="auto",
            )
            placed.append(po)
        logger.info(
            "Auto-reorder %s: placed %d, skipped %d already ordered.",
            business_date,
            len(placed),
            len(skipped),
        )
        return {"placed": placed, "skipped_existing": skipped, "count": len(placed)}


    def apply_order_priorities(
        self,
        business_date: str,
        priorities: dict[str, int],
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Set explicit per-order priorities and re-solve the day once.

        Assigns each order its own target priority (clamped 1–10), so a planner
        can raise some orders and lower others in a single re-plan. Consolidates
        with any existing priority overrides into one cumulative modification
        entry (never a growing list of per-order entries).
        """
        return self._apply_priority_changes(business_date, dict(priorities), options)

    def apply_recommendation_action(
        self,
        business_date: str,
        action: str,
        targets: dict[str, list[str]] | None = None,
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Apply a recommended fix action to the day's state and re-solve.

        Dispatches to the transform for ``action`` (e.g. alternate machines,
        add shift, reschedule maintenance, free up workers, replenish
        materials), re-runs the full deterministic pipeline on the transformed
        state, and persists the result — replacing the committed plan.
        """
        options = options or self._default_options
        try:
            rec_action = RecommendationAction(action)
        except ValueError as exc:
            raise ValidationError(
                f"Unknown recommendation action: {action}.",
                details={"action": action},
            ) from exc

        logger.info(
            "Applying fix '%s' (targets=%s) and re-solving %s.",
            rec_action,
            targets or {},
            business_date,
        )
        state = self._loader.load(business_date)
        transformed = apply_fix(
            state.model_copy(deep=True), rec_action, targets or {}
        )
        policy = self._rules.evaluate(transformed)
        entry = PlanModification(
            label=_ACTION_LABELS.get(rec_action.value, rec_action.value),
            action=rec_action.value,
            applied_at=datetime.now().isoformat(timespec="seconds"),
            targets=targets or {},
        )
        return self._finalize_replan(
            business_date, transformed, policy, options, [entry]
        )

    def apply_fixes(
        self,
        business_date: str,
        order_ids: list[str] | None = None,
        priority: int = 10,
        actions: list[tuple[str, dict[str, list[str]]]] | None = None,
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Apply several fixes in a single re-solve.

        Raises the priority of ``order_ids`` and applies each ``(action,
        targets)`` transform to the day's state, then runs the deterministic
        pipeline once and persists the result. Combining every selected fix
        into one solve avoids re-planning repeatedly.
        """
        options = options or self._default_options
        target = max(1, min(10, priority))
        order_id_set = set(order_ids or [])
        actions = actions or []

        # Validate actions up front so a bad action fails before solving.
        parsed_actions: list[tuple[RecommendationAction, dict[str, list[str]]]] = []
        for action, targets in actions:
            try:
                parsed_actions.append((RecommendationAction(action), targets or {}))
            except ValueError as exc:
                raise ValidationError(
                    f"Unknown recommendation action: {action}.",
                    details={"action": action},
                ) from exc

        logger.info(
            "Applying combined fixes on %s: priority for %s, actions %s.",
            business_date,
            sorted(order_id_set),
            [a.value for a, _ in parsed_actions],
        )
        state = self._loader.load(business_date)
        transformed = state.model_copy(deep=True)

        if order_id_set:
            transformed.production_orders = [
                o.model_copy(update={"priority": target})
                if o.order_id in order_id_set
                else o
                for o in transformed.production_orders
            ]

        for action, targets in parsed_actions:
            transformed = apply_fix(transformed, action, targets)

        policy = self._rules.evaluate(transformed)
        now = datetime.now().isoformat(timespec="seconds")
        mod_entries: list[PlanModification] = []
        if order_id_set:
            ids = sorted(order_id_set)
            mod_entries.append(
                PlanModification(
                    label=f"Raised priority of {len(ids)} order(s) to {target}: "
                    + ", ".join(ids),
                    action="RAISE_PRIORITY",
                    applied_at=now,
                    targets={"order_ids": ids},
                )
            )
        for action, targets in parsed_actions:
            mod_entries.append(
                PlanModification(
                    label=_ACTION_LABELS.get(action.value, action.value),
                    action=action.value,
                    applied_at=now,
                    targets=targets or {},
                )
            )
        return self._finalize_replan(
            business_date, transformed, policy, options, mod_entries
        )

    def _apply_modification(self, state, modification: PlanModification):
        """Re-apply one logged modification to ``state`` (for cumulative undo)."""
        if modification.action == "RAISE_PRIORITY":
            ids = list(modification.targets.get("order_ids", []))
            if ids:
                levels = modification.targets.get("priorities") or []
                level_map = {
                    oid: int(levels[i]) if i < len(levels) else 10
                    for i, oid in enumerate(ids)
                }
                state.production_orders = [
                    o.model_copy(update={"priority": level_map.get(o.order_id, 10)})
                    if o.order_id in level_map
                    else o
                    for o in state.production_orders
                ]
            return state
        try:
            rec_action = RecommendationAction(modification.action)
        except ValueError:
            return state  # unknown action — skip rather than fail the rebuild
        return apply_fix(state, rec_action, modification.targets or {})

    def remove_modification(
        self,
        business_date: str,
        applied_at: str,
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Remove one applied modification and rebuild the committed plan.

        The plan is rebuilt from the day's ORIGINAL state by re-applying every
        *remaining* modification cumulatively, then re-solving — a genuine undo
        of just the removed change. If nothing remains, the plan reverts to the
        original baseline. Downstream artifacts are recomputed; the existing
        what-if comparison is preserved.
        """
        options = options or self._default_options
        mods = self._store.load_modifications(business_date)
        if mods is None:
            raise NotFoundError(
                f"No modification log for {business_date}.",
                details={"business_date": business_date},
            )
        remaining = [m for m in mods.modifications if m.applied_at != applied_at]
        if len(remaining) == len(mods.modifications):
            raise NotFoundError(
                f"No modification applied at {applied_at} for {business_date}.",
                details={"applied_at": applied_at},
            )

        logger.info(
            "Removing modification %s for %s; rebuilding from %d remaining.",
            applied_at,
            business_date,
            len(remaining),
        )

        state = self._loader.load(business_date)
        transformed = state.model_copy(deep=True)
        for modification in remaining:
            transformed = self._apply_modification(transformed, modification)
        policy = self._rules.evaluate(transformed)

        existing_scenarios = self._store.load_scenarios(business_date)
        # If nothing remains, restore the ORIGINAL baseline plan exactly (reuse
        # the schedule the morning run persisted) instead of re-solving — a
        # re-solve would drift and could land on a worse plan than the baseline.
        baseline_schedule = self._store.load_scenario_schedule(
            business_date, ScenarioType.CURRENT_PLAN
        )
        if not remaining and baseline_schedule is not None:
            schedule = baseline_schedule
        else:
            schedule = SchedulingSolver(options).solve(transformed, policy)
        kpis = self._analytics.compute(transformed, schedule)
        risks = self._risk.detect(transformed, schedule, kpis)
        recommendations = self._recommendation.recommend(transformed, schedule, risks)
        scenario_comparison = existing_scenarios or _light_comparison(
            business_date, kpis
        )

        context = self._explanation.build(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
        )
        summary = self._explanation.summarize(context)
        result = PlanningResult(
            business_date=business_date,
            schedule=schedule,
            kpis=kpis,
            risks=risks,
            recommendations=recommendations,
            scenario_comparison=scenario_comparison,
        )
        self._store.save(result, context, summary)
        self._store.save_modifications(
            PlanModifications(
                business_date=business_date,
                baseline_kpis=mods.baseline_kpis,
                current_kpis=extract_scenario_kpis(kpis),
                modifications=remaining,
            )
        )
        return result

    def get_or_run(
        self,
        business_date: str,
        options: SolverOptions | None = None,
        *,
        force: bool = False,
    ) -> PlanningResult:
        """Return cached results if present, otherwise run the pipeline."""
        if not force and self._store.exists(business_date):
            logger.info("Serving cached results for %s.", business_date)
            return PlanningResult(
                business_date=business_date,
                schedule=self._store.load_schedule(business_date),
                kpis=self._store.load_kpis(business_date),
                risks=self._store.load_risks(business_date),
                recommendations=self._store.load_recommendations(business_date),
                scenario_comparison=self._store.load_scenarios(business_date),
            )
        return self.run(business_date, options)
