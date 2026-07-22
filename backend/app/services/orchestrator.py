"""Planning orchestration and results persistence.

Coordinates the full deterministic daily pipeline
(load -> validate -> rules -> solve -> analytics -> risk -> recommendation ->
scenario -> explanation) and persists every artifact under
``outputs/<business_date>/``. The API layer runs the pipeline through
:class:`PlanningOrchestrator` and serves cached artifacts via
:class:`ResultsStore`, so expensive solves are not repeated on every request.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.analytics import AnalyticsEngine
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
from app.recommendation import RecommendationEngine
from app.risk import RiskDetectionEngine
from app.rules import BusinessRulesEngine
from app.scenario import ScenarioPlanningEngine
from app.scenario.comparison import extract_scenario_kpis
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

        schedule = SchedulingSolver(options).solve(state, policy)
        kpis = self._analytics.compute(state, schedule)
        risks = self._risk.detect(state, schedule, kpis)
        recommendations = self._recommendation.recommend(state, schedule, risks)
        scenario_comparison = ScenarioPlanningEngine(options=options).plan(state, policy)

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
        # A fresh full run resets the modification log — this plan is the new
        # baseline that later fixes are compared against.
        base = extract_scenario_kpis(kpis)
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
    ) -> PlanningResult:
        """Solve a modified state once, persist it, and log the modifications.

        Preserves the existing what-if scenario comparison (so the Scenarios
        tab keeps its three alternatives) instead of re-solving it, and appends
        ``mod_entries`` to the day's modification log with the before/after
        KPIs used by the Current Plan tab.
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
                modifications=[*existing_entries, *mod_entries],
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

        Applies the scenario transform to the day's state, re-runs the full
        deterministic pipeline on the transformed state, and persists the
        result — replacing the previously committed plan. The recomputed
        scenario comparison uses the applied plan as its new baseline.
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

        schedule = SchedulingSolver(options).solve(transformed, policy)
        kpis = self._analytics.compute(transformed, schedule)
        risks = self._risk.detect(transformed, schedule, kpis)
        recommendations = self._recommendation.recommend(transformed, schedule, risks)
        scenario_comparison = ScenarioPlanningEngine(options=options).plan(
            transformed, policy
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
        return result

    def apply_order_priority(
        self,
        business_date: str,
        order_ids: list[str],
        priority: int = 10,
        options: SolverOptions | None = None,
    ) -> PlanningResult:
        """Raise the priority of the given orders and re-solve the day.

        Loads the day's state, sets the target orders' ``priority`` (clamped to
        1–10), re-evaluates the business rules on the modified state so the
        solver's priority weights reflect the change, then re-runs the full
        deterministic pipeline and persists the result — replacing the
        committed plan. Used to mitigate delayed-order risks by pushing the
        affected orders ahead in the schedule.
        """
        options = options or self._default_options
        target = max(1, min(10, priority))
        state = self._loader.load(business_date)

        target_ids = set(order_ids)
        present = {
            o.order_id for o in state.production_orders if o.order_id in target_ids
        }
        missing = target_ids - present
        if missing:
            raise NotFoundError(
                f"Orders not found for {business_date}: {sorted(missing)}.",
                details={"order_ids": sorted(missing)},
            )

        updated_orders = [
            o.model_copy(update={"priority": target})
            if o.order_id in target_ids
            else o
            for o in state.production_orders
        ]
        modified = state.model_copy(update={"production_orders": updated_orders})

        logger.info(
            "Raising priority to %d for orders %s on %s and re-solving.",
            target,
            sorted(target_ids),
            business_date,
        )
        policy = self._rules.evaluate(modified)
        ids = sorted(target_ids)
        entry = PlanModification(
            label=f"Raised priority of {len(ids)} order(s) to {target}: "
            + ", ".join(ids),
            action="RAISE_PRIORITY",
            applied_at=datetime.now().isoformat(timespec="seconds"),
            targets={"order_ids": ids},
        )
        return self._finalize_replan(
            business_date, modified, policy, options, [entry]
        )

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
