"""Recommendation Agent.

A thin wrapper around the existing recommendation engine - no generation,
ranking, feasibility, or priority logic is duplicated here. Reads the
FactoryState, ScheduleResult, and RiskReport from the shared context, runs the
existing engine, and stores the resulting RecommendationSet back into context.
"""

from __future__ import annotations

from collections import Counter

from app.agents.base import BaseAgent
from app.agents.context import WorkflowContext
from app.agents.contracts import RecommendationAgentOutput
from app.agents.data_agent import FACTORY_STATE_KEY
from app.agents.errors import CriticalAgentError
from app.agents.planning_agent import SCHEDULE_RESULT_KEY
from app.agents.risk_agent import RISK_REPORT_KEY
from app.agents.timing import Stopwatch
from app.domain.models.recommendation import RecommendationSet
from app.recommendation import RecommendationEngine

# Shared-context key for the produced recommendation set.
RECOMMENDATION_SET_KEY = "recommendation_set"

_HIGH_PRIORITY_THRESHOLD = 8


class RecommendationAgent(BaseAgent):
    """Generates corrective recommendations via the existing engine."""

    name = "recommendation_agent"

    def __init__(self, engine: RecommendationEngine | None = None) -> None:
        self._engine = engine or RecommendationEngine()

    def execute(self, context: WorkflowContext) -> RecommendationAgentOutput:
        risks = context.shared.get(RISK_REPORT_KEY)
        if risks is None:
            raise CriticalAgentError(
                "No RiskReport in context; the Risk Agent must run first."
            )
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
            recommendations = self._engine.recommend(state, schedule, risks)

        context.shared[RECOMMENDATION_SET_KEY] = recommendations
        self._log_set(recommendations, sw.elapsed_ms)
        return RecommendationAgentOutput(
            agent=self.name,
            business_date=context.business_date,
            recommendations=recommendations,
        )

    def _log_set(self, recommendations: RecommendationSet, duration_ms: float) -> None:
        items = recommendations.recommendations
        categories = sorted({str(r.action) for r in items})
        high_priority = sum(1 for r in items if r.priority >= _HIGH_PRIORITY_THRESHOLD)
        feasible = sum(1 for r in items if str(r.feasibility) == "FEASIBLE")
        with_impact = sum(1 for r in items if r.expected_impact)

        machines: set[str] = set()
        workers: set[str] = set()
        orders: set[str] = set()
        for rec in items:
            machines.update(rec.target_entities.get("machine_ids", []))
            workers.update(rec.target_entities.get("candidate_worker_ids", []))
            orders.update(rec.target_entities.get("order_ids", []))

        self.logger.info(
            "Recommendations in %.1f ms | total=%d categories=%s high_priority=%d "
            "feasible=%d impact_estimates=%d affected_machines=%d "
            "affected_workers=%d affected_orders=%d",
            duration_ms,
            len(items),
            categories,
            high_priority,
            feasible,
            with_impact,
            len(machines),
            len(workers),
            len(orders),
        )
