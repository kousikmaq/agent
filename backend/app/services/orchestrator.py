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
from app.analytics.deliveries import build_delivery_report
from app.analytics.materials import build_materials_report
from app.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.enums import (
    RecommendationAction,
    RecommendationFeasibility,
    RiskType,
    ScenarioType,
)
from app.domain.models.analytics import KpiSet
from app.domain.models.explanation import ExplanationContext
from app.domain.models.modifications import PlanModification, PlanModifications
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import RiskReport
from app.domain.models.scenario import ScenarioComparison, ScenarioResult
from app.domain.models.schedule import ScheduleResult
from app.explanation import ExplanationContextBuilder
from app.explanation.schema import ExplanationSummary
from app.ingestion import FactoryStateLoader, build_data_source
from app.optimization import SchedulingSolver, SolverOptions
from app.optimization.objective_spec import ObjectiveWeights, weights_for
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
    AGENT_ACTIVITY = "agent_activity.json"

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

    # --- Agent activity (autonomous actions) ------------------------------
    # Per-day feed of the autonomous actions the agent took on its most recent
    # cycle, so the Live Operations page can show the user exactly what happened
    # without them having to be watching. Rewritten each cycle that does work.
    def load_activity(self, business_date: str) -> list[dict]:
        path = self._dir(business_date) / self.AGENT_ACTIVITY
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def save_activity(self, business_date: str, events: list[dict]) -> None:
        directory = ensure_dir(self._dir(business_date))
        (directory / self.AGENT_ACTIVITY).write_text(
            json.dumps(events, indent=2), encoding="utf-8"
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
        self._loader = FactoryStateLoader(build_data_source(datasets_dir))
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
        weights: ObjectiveWeights | None = None,
        warm_start: ScheduleResult | None = None,
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

        schedule = SchedulingSolver(options).solve(
            transformed, policy, weights, warm_start=warm_start
        )
        kpis = self._analytics.compute(transformed, schedule)
        risks = self._risk.detect(transformed, schedule, kpis)
        recommendations = self._recommendation.recommend(transformed, schedule, risks)
        # A modification re-plan is layered on the ORIGINAL day state, not on a
        # committed what-if. The plan in use is therefore a modified
        # CURRENT_PLAN, not whatever scenario was previously applied: reset the
        # committed marker to CURRENT_PLAN (and refresh its row to the modified
        # KPIs) so the Scenarios tab does not keep showing a stale scenario as
        # "in use".
        if existing_scenarios is not None:
            scenario_comparison = _comparison_with_applied(
                existing_scenarios, ScenarioType.CURRENT_PLAN, kpis
            )
        else:
            scenario_comparison = _light_comparison(business_date, kpis)

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
        record_modification: bool = False,
    ) -> PlanningResult:
        """Commit a scenario's plan as the current plan for ``business_date``.

        Reuses the scenario's schedule already computed and persisted by the
        morning pipeline run — selecting a plan must NOT re-solve, so the
        committed plan is exactly the one previewed and never drifts. Only the
        downstream artifacts (risks, deliveries, recommendations) are recomputed
        against that fixed schedule. Falls back to solving once if no saved
        scenario schedule exists (e.g. a legacy day).

        When ``record_modification`` is True the commit is written to the day's
        modification log (as an ``APPLY_SCENARIO`` entry with before/after KPIs)
        so the Current Plan tab reflects it and it can be undone/reverted like
        any other change. Used by the autonomous optimiser.
        """
        options = options or self._default_options
        # Capture the pre-commit modification log + KPIs before anything is saved
        # so an optional modification entry can record the correct before/after.
        prev_mods = self._store.load_modifications(business_date)
        prev_kpis = self._store.load_kpis(business_date)
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
        if record_modification:
            if prev_mods is not None:
                baseline = prev_mods.baseline_kpis
                existing_entries = list(prev_mods.modifications)
            elif prev_kpis is not None:
                baseline = extract_scenario_kpis(prev_kpis)
                existing_entries = []
            else:
                baseline = extract_scenario_kpis(kpis)
                existing_entries = []
            # A scenario commit replaces the whole plan, so it supersedes any
            # earlier modifications: record it as the single active change.
            entry = PlanModification(
                label=f"Agent committed the '{spec.definition.name}' plan",
                action="APPLY_SCENARIO",
                applied_at=datetime.now().isoformat(timespec="seconds"),
                targets={"scenario_type": [scenario_type.value]},
            )
            self._store.save_modifications(
                PlanModifications(
                    business_date=business_date,
                    baseline_kpis=baseline,
                    current_kpis=extract_scenario_kpis(kpis),
                    modifications=[entry],
                )
            )
            _ = existing_entries  # superseded by the whole-plan commit
        return result

    def apply_planning_goal(
        self,
        business_date: str,
        weights: ObjectiveWeights,
        goal: str,
        strategy: str = "",
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Re-solve the day under an LLM-derived objective and commit the result.

        ``weights`` is a validated objective term -> weight map produced by the
        planning-goal advisor from the planner's natural-language ``goal``. The
        solver -- not the LLM -- produces the schedule, so all feasibility and
        determinism guarantees hold; the LLM only chose the objective emphasis.
        The result is committed as a modified CURRENT_PLAN (the Scenarios tab's
        four what-ifs are preserved) and logged so the Current Plan tab shows the
        goal that shaped it.
        """
        options = options or self._default_options
        state = self._loader.load(business_date)
        policy = self._rules.evaluate(state)
        label = f"Optimised for goal: {goal.strip()}"
        if strategy:
            label += f" ({strategy})"
        entry = PlanModification(
            label=label[:200],
            action="LLM_PLANNING_GOAL",
            applied_at=datetime.now().isoformat(timespec="seconds"),
            targets={},
        )
        logger.info(
            "Applying LLM planning goal for %s with weights %s.",
            business_date,
            weights,
        )
        # Warm-start from the day's committed schedule: it is always feasible for
        # the same (untransformed) state, so the re-solve can only improve on it
        # under the new objective and never returns a pathological plan.
        warm_start = self._store.load_schedule(business_date)
        return self._finalize_replan(
            business_date,
            state,
            policy,
            options,
            [entry],
            weights=weights,
            warm_start=warm_start,
        )

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
        priority_max: int = 9,
        notify: bool = False,
        options: SolverOptions | None = None,
    ) -> dict:
        """Autonomously re-plan every prioritised order that is running late.

        Inspects the committed plan and finds *all* late orders whose *display*
        priority is at most ``priority_max`` (0 = most urgent). It then raises
        the whole set in a single consolidated re-plan so as many as possible
        finish on time: the most urgent late orders are boosted to the top
        priority band and the rest are graduated just below them, preserving
        relative urgency. This is one reversible action recorded in the
        modification log. Optionally emails a risk + replan summary. Returns a
        summary and is a safe no-op when nothing needs doing.

        The default window spans every prioritised order, so a single run
        remediates all the critical late orders together rather than only the
        top one or two.
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
        late = [
            o
            for o in aggregates.order_outcomes
            if not o.on_time and o.priority >= threshold_raw
        ]
        before_otd = kpis.on_time_delivery_rate

        if not late:
            logger.info(
                "Auto-remediate %s: no prioritised late orders.", business_date
            )
            return {
                "triggered": False,
                "reason": "no high-priority late orders",
                "critical_orders": [],
                "before_otd": before_otd,
            }

        # Rank the late orders by urgency (higher raw priority first, then more
        # late first) and give them graduated target priorities so the solver
        # can distinguish the whole set while keeping every one of them above
        # ordinary orders. All of them are re-planned together in one pass.
        ranked = sorted(
            late, key=lambda o: (o.priority, o.tardiness_minutes), reverse=True
        )
        new_levels = {o.order_id: max(6, 10 - i) for i, o in enumerate(ranked)}
        critical = sorted(new_levels)

        logger.info(
            "Auto-remediate %s: %d prioritised late order(s) %s — re-planning.",
            business_date,
            len(critical),
            critical,
        )
        result = self._apply_priority_changes(business_date, new_levels, options)
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
        notify: bool = True,
    ) -> dict:
        """Place a purchase order for a material, email it, and log it for the day.

        Returns the recorded purchase order. ``mode`` marks whether it was placed
        by a human ("manual") or the agent ("auto"). Quantity defaults to the
        shortage (rounded up) when not given. ``notify=False`` skips the per-PO
        email (used by batch auto-reorder, which sends a single digest instead).
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
        email_status = self._send_po_email(item, qty, reason) if notify else "batched"
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

    def auto_reorder(self, business_date: str, notify: bool = True) -> dict:
        """Autonomously place POs for materials below safety or reorder level.

        De-duplicates against orders already placed for the day (so it runs at
        most once per material per day). Prioritises below-safety items (then
        largest shortage) and caps the run at ``auto_reorder_max_per_run`` to
        avoid a PO/email flood on a large catalog. Sends ONE digest email for
        the whole batch rather than one email per PO (``notify=False`` skips it
        so the caller can fold the result into a single combined message). Safe
        no-op when nothing qualifies.
        """
        report = build_materials_report(self._loader.load(business_date))
        already = {po["product_id"] for po in self._store.load_purchase_orders(business_date)}

        candidates = [
            line
            for line in report.lines
            if (line.below_safety or line.below_reorder) and line.product_id not in already
        ]
        # Most urgent first: below-safety, then largest shortage.
        candidates.sort(
            key=lambda ln: (not ln.below_safety, -(ln.shortage or 0.0))
        )
        cap = max(0, get_settings().auto_reorder_max_per_run)
        selected = candidates[:cap]
        deferred = len(candidates) - len(selected)

        placed: list[dict] = []
        for line in selected:
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
                notify=False,
            )
            placed.append(po)

        if placed and notify:
            self._send_reorder_digest(business_date, placed, deferred)

        logger.info(
            "Auto-reorder %s: placed %d (deferred %d over cap), %d already ordered.",
            business_date,
            len(placed),
            deferred,
            len(already),
        )
        return {
            "placed": placed,
            "count": len(placed),
            "deferred_over_cap": deferred,
        }

    def _send_reorder_digest(
        self, business_date: str, placed: list[dict], deferred: int
    ) -> str:
        """Email a single digest summarising a batch of auto-placed POs."""
        try:
            from app.notifications import EmailService

            rows = "".join(
                f"<li>{po.get('name') or po['product_id']} "
                f"(x{po['quantity']:,})</li>"
                for po in placed
            )
            more = (
                f"<p>{deferred} further item(s) were below reorder level but "
                f"deferred by the per-run cap; they will be reconsidered on the "
                f"next cycle.</p>"
                if deferred
                else ""
            )
            subject = (
                f"[PPO] Auto-reorder — {len(placed)} purchase order(s) placed "
                f"for {business_date}"
            )
            html = (
                f"<p>The agent placed {len(placed)} purchase order(s) for "
                f"materials at/below their safety or reorder level on "
                f"{business_date}:</p><ul>{rows}</ul>{more}"
            )
            text = f"{len(placed)} purchase order(s) placed for {business_date}."
            EmailService().send_html(subject, html, text_body=text)
            return "sent"
        except Exception:  # noqa: BLE001 - notifications must never break planning
            logger.exception("Auto-reorder digest email failed for %s.", business_date)
            return "error"

    # -- Autonomous plan optimisation --------------------------------------
    # Severity weights used to score a risk report: a single critical risk
    # outweighs many low ones, so the agent always prefers the plan that clears
    # the most severe risks first.
    _RISK_WEIGHTS = {"CRITICAL": 100.0, "HIGH": 10.0, "MEDIUM": 2.0, "LOW": 1.0}

    @classmethod
    def _score_risks(cls, risks: RiskReport) -> tuple[float, int, int]:
        """Return (weighted score, total count, critical+high count) for a report."""
        score = 0.0
        crit_high = 0
        for r in risks.risks:
            sev = str(r.severity)
            score += cls._RISK_WEIGHTS.get(sev, 1.0)
            if sev in ("CRITICAL", "HIGH"):
                crit_high += 1
        return score, len(risks.risks), crit_high

    def _evaluate_scenario_risk(
        self, business_date: str, spec, state
    ) -> tuple[float, int, int, float, float] | None:
        """Score a what-if scenario's risk profile without committing it.

        Reuses the scenario's morning-computed schedule (no re-solve) and runs
        the same analytics + risk detection the commit path would, so the score
        reflects exactly what the plan would look like if applied. Returns
        (risk_score, risk_count, critical_high_count, otd, cost) or ``None`` when
        the scenario has no saved schedule.
        """
        scenario_type = spec.definition.scenario_type
        saved = self._store.load_scenario_schedule(business_date, scenario_type)
        if saved is None:
            return None
        transformed = spec.transform(
            state.model_copy(deep=True), spec.definition.parameters
        )
        kpis = self._analytics.compute(transformed, saved)
        risks = self._risk.detect(transformed, saved, kpis)
        score, count, crit_high = self._score_risks(risks)
        otd = kpis.on_time_delivery_rate or 0.0
        cost = float(kpis.metrics.get("cost_total", 0.0) or 0.0)
        return score, count, crit_high, otd, cost

    def auto_optimize_plan(self, business_date: str) -> dict:
        """Commit the what-if plan that delivers the best *outcome*, not just the
        fewest risk flags.

        Ranks the committed plan and every what-if by genuine business value —
        highest on-time delivery, then lowest cost, then fewest risks as a final
        tie-break — and commits the best when it beats the current plan. Judging
        by outcome (rather than raw risk count) is deliberate: all what-ifs often
        tie on delivery, and a plain risk-flag count is skewed by un-actionable
        material risks and by capacity plans being penalised for running their
        *added* machines hot. So the winner reflects the day's real bottleneck
        and legitimately varies (overtime some days, extra shift others) instead
        of always defaulting to one lever. Safe no-op when nothing is better.
        """
        schedule = self._store.load_schedule(business_date)
        kpis = self._store.load_kpis(business_date)
        if schedule is None or kpis is None:
            return {"optimized": False, "reason": "no plan"}

        state = self._loader.load(business_date)
        current_risks = self._store.load_risks(business_date)
        if current_risks is None:
            current_risks = self._risk.detect(state, schedule, kpis)
        cur_score, cur_count, cur_crit_high = self._score_risks(current_risks)
        cur_otd = kpis.on_time_delivery_rate or 0.0
        cur_cost = float(kpis.metrics.get("cost_total", 0.0) or 0.0)

        # Rank by outcome: prefer higher on-time delivery, then lower cost, then
        # fewer risks. Never accept a plan that lowers on-time delivery.
        cur_key = (-cur_otd, cur_cost, cur_score)
        best: tuple[float, float, float, ScenarioType, int, int] | None = None
        best_key: tuple[float, float, float] | None = None
        for spec in DEFAULT_SCENARIOS:
            scenario_type = spec.definition.scenario_type
            if scenario_type == ScenarioType.CURRENT_PLAN:
                continue
            evaluated = self._evaluate_scenario_risk(business_date, spec, state)
            if evaluated is None:
                continue
            score, count, crit_high, otd, cost = evaluated
            if otd < cur_otd - 1e-9:
                continue  # never trade away on-time delivery
            key = (-otd, cost, score)
            if best_key is None or key < best_key:
                best_key = key
                best = (otd, cost, score, scenario_type, count, crit_high)

        if best is None or best_key is None or best_key >= cur_key:
            return {
                "optimized": False,
                "reason": "no better plan",
                "risk_count_before": cur_count,
                "risk_score_before": round(cur_score, 1),
            }

        otd, cost, score, scenario_type, count, crit_high = best
        self.apply_scenario(business_date, scenario_type, record_modification=True)
        logger.info(
            "Auto-optimize %s: committed '%s' (best value: OTD %.1f%%->%.1f%%, "
            "cost %.0f->%.0f, risks %d->%d).",
            business_date,
            scenario_type.value,
            cur_otd * 100,
            otd * 100,
            cur_cost,
            cost,
            cur_count,
            count,
        )
        return {
            "optimized": True,
            "scenario": str(scenario_type.value),
            "risk_count_before": cur_count,
            "risk_count_after": count,
            "critical_high_before": cur_crit_high,
            "critical_high_after": crit_high,
            "otd_before": cur_otd,
            "otd_after": otd,
            "cost_before": cur_cost,
            "cost_after": cost,
        }

    def auto_commit_best(
        self,
        business_date: str,
        min_otd_gain: float | None = None,
        max_cost_increase: float | None = None,
    ) -> dict:
        """Auto-commit the best what-if plan when it clearly beats the current one.

        Picks the scenario with the highest on-time delivery; commits it only if
        OTD improves by at least ``min_otd_gain`` AND cost rises by no more than
        ``max_cost_increase`` vs the currently committed plan. Reversible.
        """
        s = get_settings()
        min_gain = min_otd_gain if min_otd_gain is not None else s.auto_commit_min_otd_gain
        max_cost = (
            max_cost_increase
            if max_cost_increase is not None
            else s.auto_commit_max_cost_increase
        )
        scenarios = self._store.load_scenarios(business_date)
        if scenarios is None or not scenarios.results:
            return {"committed": False, "reason": "no scenarios"}
        committed = next(
            (r for r in scenarios.results if r.scenario_type == scenarios.committed_type),
            None,
        )
        if committed is None:
            return {"committed": False, "reason": "no committed row"}
        cur_otd = committed.kpis.get("on_time_delivery_rate", 0.0)
        cur_cost = committed.kpis.get("cost_total", 0.0)
        candidates = [
            r for r in scenarios.results if r.scenario_type != scenarios.committed_type
        ]
        if not candidates:
            return {"committed": False, "reason": "no alternatives"}
        best = max(candidates, key=lambda r: r.kpis.get("on_time_delivery_rate", 0.0))
        gain = best.kpis.get("on_time_delivery_rate", 0.0) - cur_otd
        cost_delta = best.kpis.get("cost_total", 0.0) - cur_cost
        summary = {
            "committed": False,
            "from": str(scenarios.committed_type.value),
            "best": str(best.scenario_type.value),
            "otd_gain": round(gain, 4),
            "cost_delta": round(cost_delta, 2),
        }
        if gain >= min_gain and cost_delta <= max_cost:
            self.apply_scenario(business_date, best.scenario_type)
            summary["committed"] = True
            logger.info(
                "Auto-commit %s: switched to '%s' (OTD +%.1f%%, cost %+.0f).",
                business_date,
                best.scenario_type.value,
                gain * 100,
                cost_delta,
            )
        else:
            summary["reason"] = "thresholds not met"
        return summary

    def auto_rebalance(
        self,
        business_date: str,
        util_threshold: float | None = None,
        alt_util_max: float | None = None,
    ) -> dict:
        """Relieve a machine bottleneck by switching to the Alternate-Machines plan.

        Triggers when the busiest machine is at/above ``util_threshold`` while
        another sits below ``alt_util_max``; applies the Alternate-Machines plan
        only if it shortens makespan or raises on-time delivery. Reversible.
        """
        from app.analytics.kpis import aggregate_schedule

        s = get_settings()
        hot = util_threshold if util_threshold is not None else s.auto_rebalance_util_threshold
        cool = alt_util_max if alt_util_max is not None else s.auto_rebalance_alt_util_max

        schedule = self._store.load_schedule(business_date)
        kpis = self._store.load_kpis(business_date)
        if schedule is None or kpis is None:
            return {"rebalanced": False, "reason": "no plan"}
        state = self._loader.load(business_date)
        agg = aggregate_schedule(state, schedule)
        utils = [m.utilization for m in agg.machine_usage]
        if not utils:
            return {"rebalanced": False, "reason": "no machine usage"}
        max_util, min_util = max(utils), min(utils)
        if not (max_util >= hot and min_util < cool):
            return {
                "rebalanced": False,
                "reason": "no bottleneck",
                "max_util": round(max_util, 3),
            }
        scenarios = self._store.load_scenarios(business_date)
        alt = (
            next(
                (r for r in scenarios.results
                 if r.scenario_type == ScenarioType.ALTERNATE_MACHINES),
                None,
            )
            if scenarios
            else None
        )
        if alt is None:
            return {"rebalanced": False, "reason": "no alternate plan"}
        cur_makespan = kpis.metrics.get("makespan_minutes", float("inf"))
        cur_otd = kpis.on_time_delivery_rate or 0.0
        alt_makespan = alt.kpis.get("makespan_minutes", float("inf"))
        alt_otd = alt.kpis.get("on_time_delivery_rate", 0.0)
        if alt_makespan < cur_makespan or alt_otd > cur_otd:
            self.apply_scenario(business_date, ScenarioType.ALTERNATE_MACHINES)
            logger.info(
                "Auto-rebalance %s: bottleneck util=%.2f -> applied Alternate Machines.",
                business_date,
                max_util,
            )
            return {
                "rebalanced": True,
                "bottleneck_util": round(max_util, 3),
                "makespan_before": cur_makespan,
                "makespan_after": alt_makespan,
            }
        return {"rebalanced": False, "reason": "alternate not better"}

    def send_morning_briefing(self, business_date: str, actions: dict) -> bool:
        """Email one daily briefing: plan summary, risk alert, and agent actions."""
        try:
            from app.notifications import EmailService

            kpis = self._store.load_kpis(business_date)
            risks = self._store.load_risks(business_date)
            settings = get_settings()
            critical = 0
            if risks is not None:
                critical = sum(
                    1
                    for r in risks.risks
                    if str(r.severity) in ("CRITICAL", "HIGH")
                )

            def pct(v: object) -> str:
                return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "n/a"

            otd = kpis.on_time_delivery_rate if kpis else None
            cost = kpis.metrics.get("cost_total") if kpis else None
            makespan = kpis.metrics.get("makespan_minutes") if kpis else None

            did: list[str] = []
            opt = actions.get("optimize") or {}
            if opt.get("optimized"):
                ob = opt.get("cost_before")
                oa = opt.get("cost_after")
                span = (
                    f" (cost ${ob:,.0f} → ${oa:,.0f})"
                    if isinstance(ob, (int, float)) and isinstance(oa, (int, float))
                    else ""
                )
                did.append(
                    f"committed the best-value '{opt.get('scenario')}' plan{span}"
                )
            rem = actions.get("remediate") or {}
            if rem.get("triggered"):
                did.append(
                    f"prioritised {len(rem.get('critical_orders', []))} late order(s)"
                )
            reo = actions.get("reorder") or {}
            if reo.get("count"):
                did.append(f"placed {reo['count']} purchase order(s)")
            cb = actions.get("commit_best") or {}
            if cb.get("committed"):
                did.append(f"switched to the '{cb.get('best')}' plan")
            rb = actions.get("rebalance") or {}
            if rb.get("rebalanced"):
                did.append("re-balanced a machine bottleneck")
            rc = actions.get("conflicts") or {}
            if rc.get("resolved"):
                did.append(f"auto-resolved {rc.get('count')} scheduling conflict(s)")
            ot = actions.get("overtime") or {}
            if ot.get("applied"):
                did.append(
                    f"enabled overtime ({ot.get('at_risk')} at-risk order(s))"
                )
            esc = actions.get("escalation") or {}
            if esc.get("escalated"):
                did.append(f"escalated {esc.get('count')} severely late order(s)")
            did_html = (
                "<ul>" + "".join(f"<li>{d}</li>" for d in did) + "</ul>"
                if did
                else "<p>No autonomous changes were needed.</p>"
            )

            # Detail sections fold in what used to be separate emails, so this
            # single briefing is the one combined notification for the run.
            details: list[str] = []
            placed = reo.get("placed") or []
            if placed:
                po_items = "".join(
                    f"<li>{po.get('name') or po['product_id']} (x{po['quantity']:,})</li>"
                    for po in placed
                )
                deferred = reo.get("deferred_over_cap") or 0
                extra = (
                    f"<p style='color:#888'>{deferred} more below reorder — deferred to "
                    f"the next cycle by the per-run cap.</p>"
                    if deferred
                    else ""
                )
                details.append(
                    f"<p><b>Purchase orders placed ({len(placed)}):</b></p>"
                    f"<ul>{po_items}</ul>{extra}"
                )
            fixes = rc.get("fixes") or []
            if fixes:
                fix_items = "".join(f"<li>{lbl}</li>" for lbl in fixes)
                details.append(
                    f"<p><b>Conflicts resolved ({len(fixes)}):</b></p><ul>{fix_items}</ul>"
                )
            esc_orders = esc.get("orders") or []
            if esc_orders:
                esc_items = "".join(
                    f"<li>{o['order_id']}: {o['days_late']} days late (due {o['due_date']})</li>"
                    for o in esc_orders
                )
                details.append(
                    f"<p style='color:#c0392b'><b>⚠ Escalated — severely late "
                    f"({esc.get('count')}):</b></p><ul>{esc_items}</ul>"
                )
            details_html = "".join(details)
            alert_html = (
                f"<p style='color:#c0392b'><b>⚠ Risk alert:</b> {critical} critical/high "
                f"risks (threshold {settings.briefing_critical_risk_threshold}).</p>"
                if critical >= settings.briefing_critical_risk_threshold
                else ""
            )
            html = (
                f"<h3>Daily plan briefing — {business_date}</h3>"
                f"<p><b>On-time delivery:</b> {pct(otd)} &nbsp; "
                f"<b>Est. cost:</b> {('$%0.0f' % cost) if isinstance(cost,(int,float)) else 'n/a'} &nbsp; "
                f"<b>Makespan:</b> {(f'{makespan/1440:.1f} d') if isinstance(makespan,(int,float)) else 'n/a'}</p>"
                f"{alert_html}"
                f"<p><b>What the agent did overnight:</b></p>{did_html}"
                f"{details_html}"
                f"<p style='color:#888'>Automated briefing from the Production Planning Agent.</p>"
            )
            EmailService().send_html(
                subject=f"[PPO] Daily plan briefing — {business_date}",
                html_body=html,
            )
            logger.info("Morning briefing emailed for %s.", business_date)
            return True
        except Exception:  # noqa: BLE001 - notifications must never break planning
            logger.exception("Morning briefing failed for %s.", business_date)
            return False

    @staticmethod
    def _send_summary_email(subject: str, html: str, to: str | None = None) -> bool:
        """Send a summary/notification email; never raises (returns a flag)."""
        try:
            from app.notifications import EmailService

            EmailService().send_html(subject=subject, html_body=html, to=to)
            return True
        except Exception:  # noqa: BLE001 - notifications must never break planning
            logger.exception("Summary email failed: %s", subject)
            return False

    def resolve_conflicts(self, business_date: str, notify: bool = True) -> dict:
        """Auto-resolve simple conflicts and email the supervisor a summary.

        Applies feasible reassign-worker / reschedule-maintenance fixes for any
        worker- or maintenance-conflict risks (one combined re-solve, logged and
        reversible), then emails a summary of actions to the supervisor.
        ``notify=False`` skips the standalone email so the caller can fold the
        result into a single combined message.
        """
        risks = self._store.load_risks(business_date)
        recs = self._store.load_recommendations(business_date)
        if risks is None or recs is None:
            return {"resolved": False, "reason": "no data", "count": 0}
        conflict_types = {RiskType.WORKER_CONFLICT, RiskType.MAINTENANCE_CONFLICT}
        conflict_ids = {r.risk_id for r in risks.risks if r.risk_type in conflict_types}
        if not conflict_ids:
            return {"resolved": False, "reason": "no conflicts", "count": 0}
        safe = {
            RecommendationAction.ASSIGN_ALTERNATE_WORKER,
            RecommendationAction.RESCHEDULE_MAINTENANCE,
        }
        seen: set = set()
        actions: list[tuple[str, dict[str, list[str]]]] = []
        labels: list[str] = []
        for rec in recs.recommendations:
            if rec.feasibility != RecommendationFeasibility.FEASIBLE:
                continue
            if rec.action not in safe:
                continue
            if not (set(rec.addresses_risk_ids) & conflict_ids):
                continue
            key = (
                rec.action.value,
                tuple(sorted((k, tuple(v)) for k, v in rec.target_entities.items())),
            )
            if key in seen:
                continue
            seen.add(key)
            actions.append((rec.action.value, rec.target_entities))
            labels.append(rec.title)
        if not actions:
            return {"resolved": False, "reason": "no feasible conflict fixes", "count": 0}
        self.apply_fixes(business_date, actions=actions)
        s = get_settings()
        to = s.supervisor_email or s.alert_email_to
        items = "".join(f"<li>{lbl}</li>" for lbl in labels)
        html = (
            f"<h3>Conflicts auto-resolved — {business_date}</h3>"
            f"<p>The agent resolved <b>{len(actions)}</b> scheduling conflict(s) "
            f"and re-planned the day:</p><ul>{items}</ul>"
            f"<p style='color:#888'>Reversible actions recorded in the Current Plan log.</p>"
        )
        emailed = False
        if notify:
            emailed = self._send_summary_email(
                f"[PPO] Conflicts auto-resolved — {business_date}", html, to=to
            )
        logger.info(
            "Auto-resolve conflicts %s: applied %d fix(es).", business_date, len(actions)
        )
        return {
            "resolved": True,
            "count": len(actions),
            "emailed": emailed,
            "fixes": labels,
        }

    def overtime_on_risk(self, business_date: str, threshold: int | None = None) -> dict:
        """Apply the Overtime plan when delivery risk is high and it improves OTD."""
        s = get_settings()
        thr = threshold if threshold is not None else s.overtime_risk_threshold
        schedule = self._store.load_schedule(business_date)
        kpis = self._store.load_kpis(business_date)
        if schedule is None or kpis is None:
            return {"applied": False, "reason": "no plan"}
        state = self._loader.load(business_date)
        rep = build_delivery_report(state, schedule)
        at_risk = rep.at_risk + rep.late
        if at_risk < thr:
            return {"applied": False, "reason": "risk below threshold", "at_risk": at_risk}
        scenarios = self._store.load_scenarios(business_date)
        ot = (
            next(
                (r for r in scenarios.results
                 if r.scenario_type == ScenarioType.OVERTIME_ENABLED),
                None,
            )
            if scenarios
            else None
        )
        cur_otd = kpis.on_time_delivery_rate or 0.0
        if ot is not None and ot.kpis.get("on_time_delivery_rate", 0.0) > cur_otd:
            self.apply_scenario(business_date, ScenarioType.OVERTIME_ENABLED)
            logger.info(
                "Overtime-on-risk %s: %d at-risk -> applied Overtime.",
                business_date,
                at_risk,
            )
            return {
                "applied": True,
                "at_risk": at_risk,
                "otd_after": ot.kpis.get("on_time_delivery_rate"),
            }
        return {"applied": False, "reason": "overtime not better", "at_risk": at_risk}

    def check_escalation(self, business_date: str, notify: bool = True) -> dict:
        """Escalate by email when orders are projected late beyond the threshold.

        ``notify=False`` skips the standalone email so the caller can fold the
        escalation into a single combined message.
        """
        s = get_settings()
        schedule = self._store.load_schedule(business_date)
        if schedule is None:
            return {"escalated": False, "reason": "no plan"}
        state = self._loader.load(business_date)
        rep = build_delivery_report(state, schedule)
        thr_min = max(0, s.escalation_lateness_days) * 1440
        late = sorted(
            (ln for ln in rep.lines if ln.tardiness_minutes >= thr_min),
            key=lambda ln: ln.tardiness_minutes,
            reverse=True,
        )
        if len(late) < max(1, s.escalation_min_orders):
            return {"escalated": False, "count": len(late)}
        to = s.escalation_email or s.supervisor_email or s.alert_email_to
        late_orders = [
            {
                "order_id": ln.order_id,
                "days_late": round(ln.tardiness_minutes / 1440, 1),
                "due_date": ln.due_date,
            }
            for ln in late[:20]
        ]
        items = "".join(
            f"<li>{o['order_id']}: {o['days_late']} days late (due {o['due_date']})</li>"
            for o in late_orders
        )
        html = (
            f"<h3 style='color:#c0392b'>\u26a0 Delivery escalation — {business_date}</h3>"
            f"<p><b>{len(late)}</b> order(s) are projected late by "
            f"\u2265 {s.escalation_lateness_days} days:</p><ul>{items}</ul>"
            f"<p style='color:#888'>Automated escalation from the Production Planning Agent.</p>"
        )
        emailed = False
        if notify:
            emailed = self._send_summary_email(
                f"[PPO] ESCALATION: {len(late)} order(s) severely late — {business_date}",
                html,
                to=to,
            )
        logger.info("Escalation %s: %d order(s) >= %d days late.", business_date, len(late), s.escalation_lateness_days)
        return {"escalated": True, "count": len(late), "emailed": emailed, "orders": late_orders}

    def run_autonomy(self, business_date: str, respect_flags: bool = True) -> dict:
        """Run the autonomous action bundle for a day and return a combined summary.

        Order (a coherent decision tree so plan changes never conflict):
        1. reorder low materials (orthogonal to the schedule);
        2. pick the plan — only the first that applies changes the committed plan:
           a. resolve simple conflicts (correctness first);
           b. commit the lowest-risk what-if plan (clears capacity, machine-
              overload and delivery risks in one re-plan);
           c. prioritise high-priority late orders (fallback when no what-if is
              better);
        3. escalate severely late orders by email (orthogonal notification);
        4. email a daily briefing summarising everything.

        When ``respect_flags`` is True each step runs only if its setting is on
        (used by the scheduler); when False every step is considered
        (manual/on-demand).
        """
        s = get_settings()
        summary: dict = {}

        if not respect_flags or s.auto_reorder_enabled:
            summary["reorder"] = self.auto_reorder(business_date, notify=False)

        plan_changed = False
        if not respect_flags or s.auto_resolve_conflicts_enabled:
            rc = self.resolve_conflicts(business_date, notify=False)
            summary["conflicts"] = rc
            plan_changed = bool(rc.get("resolved"))
        # Risk-minimising plan selection supersedes the old commit-best / overtime
        # / rebalance trio: it evaluates every what-if by its resulting risk
        # profile and commits the best, so it fires even when on-time delivery is
        # already 100% but capacity/overload risks remain.
        if not plan_changed and (not respect_flags or s.auto_commit_best_enabled):
            opt = self.auto_optimize_plan(business_date)
            summary["optimize"] = opt
            plan_changed = bool(opt.get("optimized"))
        if not plan_changed and (not respect_flags or s.auto_replan_enabled):
            rem = self.auto_remediate(
                business_date, priority_max=s.auto_replan_priority_max, notify=False
            )
            summary["remediate"] = rem
            plan_changed = bool(rem.get("triggered"))

        if not respect_flags or s.auto_escalation_enabled:
            summary["escalation"] = self.check_escalation(business_date, notify=False)

        # Single consolidated notification: every sub-step above ran with its own
        # email suppressed, so the run emits ONE combined briefing covering the
        # reorder, conflicts, plan change and escalation. Sent whenever the run
        # actually did something (or briefing is explicitly enabled), so a
        # suppressed sub-email is never silently lost.
        did_work = (
            bool((summary.get("reorder") or {}).get("count"))
            or bool((summary.get("conflicts") or {}).get("resolved"))
            or plan_changed
            or bool((summary.get("escalation") or {}).get("escalated"))
        )
        if not respect_flags or s.auto_briefing_enabled or did_work:
            summary["briefing_sent"] = self.send_morning_briefing(business_date, summary)

        self._record_autonomy_activity(business_date, summary)
        return summary

    def _record_autonomy_activity(self, business_date: str, summary: dict) -> None:
        """Persist a per-day feed of the autonomous actions actually taken.

        Only real actions are recorded (a step that evaluated but did nothing is
        skipped), so the Live Operations timeline reflects exactly what happened.
        The log is rewritten only when at least one action occurred, so a no-op
        cycle never erases an earlier cycle's history for the day.
        """
        now = datetime.now().isoformat(timespec="seconds")
        events: list[dict] = []

        def add(
            kind: str,
            title: str,
            detail: str,
            *,
            reversible: bool = False,
            emailed: bool = False,
            impact: str | None = None,
            trigger: str | None = None,
        ) -> None:
            events.append(
                {
                    "at": now,
                    "kind": kind,
                    "title": title,
                    "detail": detail,
                    "reversible": reversible,
                    "emailed": emailed,
                    "impact": impact,
                    "trigger": trigger,
                }
            )

        reo = summary.get("reorder") or {}
        if reo.get("count"):
            placed = reo.get("placed") or []

            def _po_label(po: object) -> str:
                if isinstance(po, dict):
                    pid = po.get("product_id") or po.get("material_id") or "?"
                    qty = po.get("quantity")
                    return f"{pid} x{qty}" if qty is not None else str(pid)
                return str(po)

            listing = (
                f": {', '.join(_po_label(p) for p in placed[:6])}" if placed else ""
            )
            add(
                "reorder",
                "Reordered low materials",
                f"Placed {reo['count']} purchase order(s){listing}",
                emailed=True,
                trigger="Materials below safety / reorder point",
            )

        rc = summary.get("conflicts") or {}
        if rc.get("resolved"):
            add(
                "conflict",
                "Resolved scheduling conflicts",
                f"Auto-resolved {rc.get('count')} conflict(s) and re-planned the day",
                reversible=True,
                emailed=bool(rc.get("emailed")),
                trigger="Worker / maintenance conflicts detected",
            )

        opt = summary.get("optimize") or {}
        if opt.get("optimized"):
            before = opt.get("risk_count_before")
            after = opt.get("risk_count_after")
            cb0 = opt.get("cost_before")
            ca0 = opt.get("cost_after")
            impact = None
            if isinstance(cb0, (int, float)) and isinstance(ca0, (int, float)):
                impact = f"Cost ${cb0:,.0f} → ${ca0:,.0f}"
                if isinstance(before, int) and isinstance(after, int):
                    impact += f" (risks {before} → {after})"
            add(
                "optimize",
                "Committed the best-value plan",
                f"Switched to the '{opt.get('scenario')}' plan (best on-time "
                f"delivery at the lowest cost)",
                reversible=True,
                impact=impact,
                trigger="A what-if plan improved delivery/cost without lowering on-time delivery",
            )

        cb = summary.get("commit_best") or {}
        if cb.get("committed"):
            gain = cb.get("otd_gain")
            cost = cb.get("cost_delta")
            impact = None
            if isinstance(gain, (int, float)):
                impact = f"OTD {'+' if gain >= 0 else ''}{gain * 100:.1f}%"
                if isinstance(cost, (int, float)):
                    impact += f", cost {cost:+,.0f}"
            add(
                "commit",
                "Committed the best plan",
                f"Switched to the '{cb.get('best')}' plan",
                reversible=True,
                impact=impact,
                trigger="A what-if plan cleared the improvement thresholds",
            )

        ot = summary.get("overtime") or {}
        if ot.get("applied"):
            otd = ot.get("otd_after")
            impact = f"OTD → {otd * 100:.1f}%" if isinstance(otd, (int, float)) else None
            add(
                "overtime",
                "Enabled overtime",
                f"Delivery risk was high ({ot.get('at_risk')} at-risk order(s))",
                reversible=True,
                impact=impact,
                trigger="At-risk orders reached the overtime threshold",
            )

        rem = summary.get("remediate") or {}
        if rem.get("triggered"):
            orders = rem.get("critical_orders") or []
            listing = f": {', '.join(orders[:6])}" if orders else ""
            before = rem.get("before_otd")
            after = rem.get("after_otd")
            impact = None
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                impact = f"OTD {before * 100:.1f}% → {after * 100:.1f}%"
            add(
                "remediate",
                "Prioritised late orders",
                f"Prioritised {len(orders)} late order(s){listing}",
                reversible=True,
                emailed=bool(rem.get("emailed")),
                impact=impact,
                trigger="Prioritised orders were running late",
            )

        rb = summary.get("rebalance") or {}
        if rb.get("rebalanced"):
            mb = rb.get("makespan_before")
            ma = rb.get("makespan_after")
            impact = None
            if isinstance(mb, (int, float)) and isinstance(ma, (int, float)):
                impact = f"Makespan {mb / 1440:.1f}d → {ma / 1440:.1f}d"
            add(
                "rebalance",
                "Re-balanced a bottleneck",
                "Applied the Alternate-Machines plan to relieve a hot machine",
                reversible=True,
                impact=impact,
                trigger="A machine hit a utilization bottleneck",
            )

        esc = summary.get("escalation") or {}
        if esc.get("escalated"):
            add(
                "escalation",
                "Escalated severely late orders",
                f"Escalated {esc.get('count')} order(s) by email to the supervisor",
                emailed=bool(esc.get("emailed")),
                trigger="Orders projected late beyond the escalation threshold",
            )

        if summary.get("briefing_sent"):
            add(
                "briefing",
                "Sent the daily briefing",
                "Emailed a plan summary with KPIs, risks and the actions taken",
                emailed=True,
            )

        if events:
            self._store.save_activity(business_date, events)

    def autonomy_status(self, business_date: str) -> list[dict]:
        """The full catalogue of autonomous capabilities with per-item status.

        Every capability is returned, whether or not it fired on the most recent
        cycle: the ones that acted carry their recorded detail, and the rest are
        marked standing by with the (settings-derived, never hard-coded)
        condition that would trigger them. Powers the Live Operations feed so the
        user sees both what the agent did and what it is watching for.
        """
        s = get_settings()
        done = {
            str(e.get("kind")): e for e in self._store.load_activity(business_date)
        }

        catalogue: list[tuple[str, str, str, bool]] = [
            (
                "reorder",
                "Reorder low materials",
                "Runs when materials fall below their safety or reorder point.",
                s.auto_reorder_enabled,
            ),
            (
                "conflict",
                "Resolve scheduling conflicts",
                "Runs when worker or maintenance conflicts are detected.",
                s.auto_resolve_conflicts_enabled,
            ),
            (
                "optimize",
                "Commit the lowest-risk plan",
                "Runs when a what-if plan cuts overall risk without lowering "
                "on-time delivery.",
                s.auto_commit_best_enabled,
            ),
            (
                "remediate",
                "Prioritise late orders",
                "Runs when prioritised orders are running late and no what-if "
                "plan is better.",
                s.auto_replan_enabled,
            ),
            (
                "escalation",
                "Escalate severely late orders",
                f"Runs when orders are projected at least "
                f"{s.escalation_lateness_days} day(s) late.",
                s.auto_escalation_enabled,
            ),
            (
                "briefing",
                "Send the daily briefing",
                "Runs after each daily cycle to summarise the plan and actions.",
                s.auto_briefing_enabled,
            ),
        ]

        status: list[dict] = []
        for kind, title, condition, enabled in catalogue:
            event = done.get(kind)
            status.append(
                {
                    "kind": kind,
                    "title": title,
                    "done": event is not None,
                    "condition": condition,
                    "enabled": bool(enabled),
                    "detail": event.get("detail") if event else None,
                    "impact": event.get("impact") if event else None,
                    "trigger": event.get("trigger") if event else None,
                    "reversible": bool(event.get("reversible")) if event else False,
                    "emailed": bool(event.get("emailed")) if event else False,
                    "at": event.get("at") if event else None,
                }
            )
        return status

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
        if modification.action == "APPLY_SCENARIO":
            # A committed what-if plan: re-apply its deterministic transform so a
            # cumulative rebuild reproduces the same plan shape.
            values = modification.targets.get("scenario_type", [])
            if not values:
                return state
            try:
                scenario_type = ScenarioType(values[0])
            except ValueError:
                return state
            spec = next(
                (
                    s
                    for s in DEFAULT_SCENARIOS
                    if s.definition.scenario_type == scenario_type
                ),
                None,
            )
            if spec is None:
                return state
            return spec.transform(state, spec.definition.parameters)
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
        # The rebuilt plan is the original baseline plus any remaining
        # modifications, i.e. a CURRENT_PLAN variant, so mark CURRENT_PLAN as the
        # committed plan rather than leaving a previously applied scenario stale.
        if existing_scenarios is not None:
            scenario_comparison = _comparison_with_applied(
                existing_scenarios, ScenarioType.CURRENT_PLAN, kpis
            )
        else:
            scenario_comparison = _light_comparison(business_date, kpis)

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

    def revert_to_original(
        self,
        business_date: str,
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Discard all modifications and restore the original baseline plan (fast).

        Reuses the baseline schedule the morning run persisted (no re-solve and
        no re-run of the four what-if scenarios), recomputes only the lightweight
        downstream analytics from the original state, clears the modification
        log, and marks the baseline as the committed plan. This makes reverting
        near-instant compared with re-running the full pipeline.
        """
        options = options or self._default_options
        mods = self._store.load_modifications(business_date)
        state = self._loader.load(business_date)

        baseline_schedule = self._store.load_scenario_schedule(
            business_date, ScenarioType.CURRENT_PLAN
        )
        if baseline_schedule is not None:
            schedule = baseline_schedule
        else:
            policy = self._rules.evaluate(state)
            schedule = SchedulingSolver(options).solve(state, policy)

        kpis = self._analytics.compute(state, schedule)
        risks = self._risk.detect(state, schedule, kpis)
        recommendations = self._recommendation.recommend(state, schedule, risks)

        existing = self._store.load_scenarios(business_date)
        if existing is not None:
            scenario_comparison = _comparison_with_applied(
                existing, ScenarioType.CURRENT_PLAN, kpis
            )
        else:
            scenario_comparison = _light_comparison(business_date, kpis)

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
                baseline_kpis=(
                    mods.baseline_kpis if mods else extract_scenario_kpis(kpis)
                ),
                current_kpis=extract_scenario_kpis(kpis),
                modifications=[],
            )
        )
        logger.info("Reverted %s to the original baseline plan.", business_date)
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
