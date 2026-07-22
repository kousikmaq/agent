"""Analytics Agent.

A thin wrapper around the existing analytics services - no KPI logic is
duplicated here:
- AnalyticsEngine (computes the KpiSet)
- build_analytics_facts (curated structured facts)

Reads the ScheduleResult and FactoryState from the shared context, computes the
KPIs and facts, and stores both back into the context.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import WorkflowContext
from app.agents.contracts import AnalyticsAgentOutput
from app.agents.data_agent import FACTORY_STATE_KEY
from app.agents.errors import CriticalAgentError
from app.agents.planning_agent import SCHEDULE_RESULT_KEY
from app.agents.timing import Stopwatch
from app.analytics import AnalyticsEngine, build_analytics_facts

# Shared-context keys for the produced artifacts.
KPIS_KEY = "kpis"
ANALYTICS_FACTS_KEY = "analytics_facts"


class AnalyticsAgent(BaseAgent):
    """Computes KPIs and analytics facts from the generated schedule."""

    name = "analytics_agent"

    def __init__(self, engine: AnalyticsEngine | None = None) -> None:
        self._engine = engine or AnalyticsEngine()

    def execute(self, context: WorkflowContext) -> AnalyticsAgentOutput:
        schedule = context.shared.get(SCHEDULE_RESULT_KEY)
        if schedule is None:
            raise CriticalAgentError(
                "No ScheduleResult in context; the Planning Agent must run first."
            )
        state = context.shared.get(FACTORY_STATE_KEY)
        if state is None:
            raise CriticalAgentError(
                "No FactoryState in context; the Data Agent must run first."
            )

        with Stopwatch() as sw:
            kpis = self._engine.compute(state, schedule)
            facts = build_analytics_facts(state, schedule, kpis)

        context.shared[KPIS_KEY] = kpis
        context.shared[ANALYTICS_FACTS_KEY] = facts

        bottleneck = self._bottleneck(facts)
        self.logger.info(
            "Analytics in %.1f ms | kpis=%d machine_util=%s worker_util=n/a "
            "throughput=%s makespan=%s otd=%s wip=%s bottleneck=%s",
            sw.elapsed_ms,
            len(kpis.metrics),
            kpis.average_machine_utilization,
            kpis.metrics.get("scheduled_orders"),
            kpis.metrics.get("makespan_minutes"),
            kpis.on_time_delivery_rate,
            kpis.work_in_progress,
            bottleneck,
        )

        return AnalyticsAgentOutput(
            agent=self.name,
            business_date=context.business_date,
            kpis=kpis,
        )

    @staticmethod
    def _bottleneck(facts) -> str:
        """Return the most-utilized machine id (bottleneck), or 'n/a'."""
        if not facts.machine_utilization:
            return "n/a"
        top = max(facts.machine_utilization, key=lambda m: m.utilization)
        return f"{top.machine_id} ({top.utilization:.0%})"
