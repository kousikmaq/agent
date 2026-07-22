"""Recommendation Engine.

Orchestrates the independent generators over a shared context and assembles the
immutable, deduplicated, priority-sorted :class:`RecommendationSet`. Fully
deterministic and read-only: it proposes corrective actions but never mutates
the committed schedule.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from app.core.logging import get_logger
from app.domain.models.factory_state import FactoryState
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import RiskReport
from app.domain.models.schedule import ScheduleResult
from app.recommendation.generators import GENERATORS
from app.recommendation.result import (
    RecommendationBuilder,
    RecommendationContext,
    build_recommendation_context,
)

logger = get_logger(__name__)

Generator = Callable[[RecommendationContext, RecommendationBuilder], None]


class RecommendationEngine:
    """Maps detected risks to actionable, feasibility-checked recommendations."""

    def __init__(self, generators: Iterable[Generator] | None = None) -> None:
        """Create the engine.

        Parameters
        ----------
        generators:
            Optional override of the generator set (for testing or custom
            playbooks). Defaults to the full :data:`GENERATORS` pipeline.
        """
        self._generators: tuple[Generator, ...] = (
            tuple(generators) if generators is not None else GENERATORS
        )

    def recommend(
        self,
        state: FactoryState,
        schedule: ScheduleResult,
        risk_report: RiskReport,
    ) -> RecommendationSet:
        """Generate recommendations addressing the detected risks."""
        context = build_recommendation_context(state, schedule, risk_report)
        builder = RecommendationBuilder(state.business_date)

        for generator in self._generators:
            generator(context, builder)

        result = builder.build()
        logger.info(
            "Recommendation engine for %s produced %d recommendation(s) for %d risk(s).",
            state.business_date,
            len(result.recommendations),
            len(risk_report.risks),
        )
        return result
