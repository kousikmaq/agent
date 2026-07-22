"""Recommendation Engine.

Deterministically maps detected risks to actionable, feasibility-checked
recommendations (alternate machine/worker, split batch, reschedule maintenance,
approve overtime, expedite/replenish materials). Proposes only - never mutates
the committed schedule. No ML, no LLM.
"""

from __future__ import annotations

from app.recommendation.engine import RecommendationEngine
from app.recommendation.result import (
    RecommendationBuilder,
    RecommendationContext,
    build_recommendation_context,
)

__all__ = [
    "RecommendationEngine",
    "RecommendationContext",
    "RecommendationBuilder",
    "build_recommendation_context",
]
