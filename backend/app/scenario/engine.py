"""Scenario Planning Engine.

For each configured scenario, clones the factory state, applies the scenario
transform, re-runs the deterministic CP-SAT solver, computes KPIs, and compares
them against the baseline (current plan). Re-using the same solver guarantees an
apples-to-apples comparison; no parallel scheduling logic is maintained.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.analytics import AnalyticsEngine
from app.core.logging import get_logger
from app.domain.enums import ScenarioType
from app.domain.models.analytics import KpiSet
from app.domain.models.factory_state import FactoryState
from app.domain.models.scenario import ScenarioComparison, ScenarioResult
from app.domain.models.schedule import ScheduleResult
from app.optimization import SchedulingSolver, SolverOptions
from app.optimization.objective_spec import weights_for
from app.rules.policy import RulePolicy
from app.scenario.comparison import compute_kpi_deltas, extract_scenario_kpis
from app.scenario.definitions import DEFAULT_SCENARIOS, ScenarioSpec

logger = get_logger(__name__)


class ScenarioPlanningEngine:
    """Runs and compares multiple planning scenarios."""

    def __init__(
        self,
        scenarios: Iterable[ScenarioSpec] | None = None,
        options: SolverOptions | None = None,
    ) -> None:
        """Create the engine.

        Parameters
        ----------
        scenarios:
            Optional override of the scenario set. Defaults to
            :data:`DEFAULT_SCENARIOS` (current, overtime, alternate machines,
            additional shift).
        options:
            Solver options applied to every scenario solve.
        """
        self._scenarios: tuple[ScenarioSpec, ...] = (
            tuple(scenarios) if scenarios is not None else DEFAULT_SCENARIOS
        )
        self._options = options or SolverOptions.from_settings()
        self._solver = SchedulingSolver(self._options)
        self._analytics = AnalyticsEngine()

    def plan(
        self,
        state: FactoryState,
        policy: RulePolicy,
        injected: dict[ScenarioType, KpiSet] | None = None,
        baseline_schedule: ScheduleResult | None = None,
        schedules_out: dict[ScenarioType, ScheduleResult] | None = None,
    ) -> ScenarioComparison:
        """Solve and compare every scenario, returning the comparison.

        ``state`` must always be the day's *original* dataset state so the
        comparison is stable and never compounds a previously applied scenario
        on top of itself.

        For any scenario whose type appears in ``injected``, that scenario's
        row reuses the supplied KPIs verbatim instead of re-solving. This lets
        the committed plan (top KPI bar, Overview, assistant) share the exact
        same numbers as its row in the Scenarios tab -- the CP-SAT solver runs
        several parallel workers and is not bit-for-bit reproducible, so a
        separate re-solve of the same state can otherwise diverge.

        ``baseline_schedule`` (the committed Current-Plan schedule) is used to
        warm-start every what-if solve. Since scenarios only *add* resources,
        the baseline plan is feasible in each, so warm-starting guarantees a
        scenario is never worse than the baseline merely because its larger
        model is harder to solve in the time budget.
        """
        injected = injected or {}
        results: list[ScenarioResult] = []
        baseline_result: ScenarioResult | None = None
        baseline_type = ScenarioType.CURRENT_PLAN

        for spec in self._scenarios:
            scenario_type = spec.definition.scenario_type
            if scenario_type in injected:
                result = ScenarioResult(
                    scenario_type=scenario_type,
                    name=spec.definition.name,
                    kpis=extract_scenario_kpis(injected[scenario_type]),
                    is_baseline=spec.is_baseline,
                )
                # The injected (committed) scenario's schedule IS the baseline.
                if schedules_out is not None and baseline_schedule is not None:
                    schedules_out[scenario_type] = baseline_schedule
            else:
                result, schedule = self._run_scenario(
                    state, policy, spec, baseline_schedule
                )
                if schedules_out is not None:
                    schedules_out[scenario_type] = schedule
            results.append(result)
            if spec.is_baseline:
                baseline_result = result
                baseline_type = scenario_type

        # Fall back to the first result as baseline if none flagged.
        if baseline_result is None and results:
            baseline_result = results[0]
            baseline_type = results[0].scenario_type

        deltas = (
            compute_kpi_deltas(baseline_result, results) if baseline_result else {}
        )

        logger.info(
            "Scenario planning for %s compared %d scenario(s).",
            state.business_date,
            len(results),
        )
        return ScenarioComparison(
            business_date=state.business_date,
            baseline_type=baseline_type,
            results=results,
            kpi_deltas=deltas,
        )

    def _run_scenario(
        self,
        state: FactoryState,
        policy: RulePolicy,
        spec: ScenarioSpec,
        baseline_schedule: ScheduleResult | None = None,
    ) -> tuple[ScenarioResult, ScheduleResult]:
        """Clone, transform, solve, and score a single scenario.

        Returns both the scored result and the full schedule so the caller can
        persist it for later reuse when the scenario is committed.
        """
        # Deep copy so scenarios never affect one another or the original.
        transformed = spec.transform(state.model_copy(deep=True), spec.definition.parameters)
        schedule = self._solver.solve(
            transformed,
            policy,
            weights_for(spec.definition.scenario_type),
            warm_start=baseline_schedule,
        )
        kpis = self._analytics.compute(transformed, schedule)

        logger.info(
            "Scenario '%s': status=%s, makespan=%s",
            spec.definition.name,
            schedule.status,
            schedule.makespan_minutes,
        )
        return (
            ScenarioResult(
                scenario_type=spec.definition.scenario_type,
                name=spec.definition.name,
                kpis=extract_scenario_kpis(kpis),
                is_baseline=spec.is_baseline,
            ),
            schedule,
        )
