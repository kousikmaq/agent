"""Scenario Planning Agent.

A thin wrapper around the existing scenario engine - no scenario definitions,
transforms, or comparison logic is duplicated here. Reads the FactoryState and
RulePolicy (and requires a baseline ScheduleResult) from the shared context,
runs the existing engine, and stores the ScenarioComparison back into context.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import WorkflowContext
from app.agents.contracts import ScenarioAgentOutput
from app.agents.data_agent import FACTORY_STATE_KEY
from app.agents.errors import CriticalAgentError
from app.agents.planning_agent import RULE_POLICY_KEY, SCHEDULE_RESULT_KEY
from app.agents.timing import Stopwatch
from app.domain.models.scenario import ScenarioComparison
from app.optimization import SolverOptions
from app.scenario import ScenarioPlanningEngine

# Shared-context key for the produced scenario comparison.
SCENARIO_COMPARISON_KEY = "scenario_comparison"


class ScenarioAgent(BaseAgent):
    """Runs and compares planning scenarios via the existing engine."""

    name = "scenario_agent"

    def __init__(
        self,
        options: SolverOptions | None = None,
        engine: ScenarioPlanningEngine | None = None,
    ) -> None:
        self._options = options or SolverOptions.from_settings()
        self._engine = engine

    def execute(self, context: WorkflowContext) -> ScenarioAgentOutput:
        # A baseline schedule must exist before scenarios can be compared.
        if context.shared.get(SCHEDULE_RESULT_KEY) is None:
            raise CriticalAgentError(
                "No baseline ScheduleResult in context; the Planning Agent must "
                "run first."
            )
        state = context.shared.get(FACTORY_STATE_KEY)
        if state is None:
            raise CriticalAgentError(
                "No FactoryState in context; the Data Agent must run first."
            )
        policy = context.shared.get(RULE_POLICY_KEY)
        if policy is None:
            raise CriticalAgentError(
                "No RulePolicy in context; the Planning Agent must run first."
            )

        engine = self._engine or ScenarioPlanningEngine(options=self._options)
        with Stopwatch() as sw:
            comparison = engine.plan(state, policy)

        context.shared[SCENARIO_COMPARISON_KEY] = comparison
        self._log_comparison(comparison, sw.elapsed_ms)
        return ScenarioAgentOutput(
            agent=self.name,
            business_date=context.business_date,
            scenario_comparison=comparison,
        )

    def _log_comparison(
        self, comparison: ScenarioComparison, duration_ms: float
    ) -> None:
        best = self._best_scenario(comparison)
        deltas = comparison.kpi_deltas.get(best, {}) if best else {}
        improvements = sum(
            1
            for name, d in comparison.kpi_deltas.items()
            if d.get("makespan_minutes", 0) < 0
        )
        self.logger.info(
            "Scenario planning in %.1f ms | scenarios=%d solver_time_per_scenario=n/a "
            "improvements=%d makespan_delta=%s otd_delta=%s utilization_delta=%s "
            "cost_delta=n/a best=%s",
            duration_ms,
            len(comparison.results),
            improvements,
            deltas.get("makespan_minutes"),
            deltas.get("on_time_delivery_rate"),
            deltas.get("average_machine_utilization"),
            best or "n/a",
        )

    @staticmethod
    def _best_scenario(comparison: ScenarioComparison) -> str | None:
        candidates = [
            r for r in comparison.results if "makespan_minutes" in r.kpis
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda r: r.kpis["makespan_minutes"]).name
