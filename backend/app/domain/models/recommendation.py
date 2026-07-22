"""Recommendation DTOs.

Output structures produced by the Recommendation Engine (later phase). Each
recommendation proposes a concrete corrective action for one or more detected
risks; recommendations never mutate the committed schedule.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.enums import RecommendationAction, RecommendationFeasibility
from app.domain.models.base import FrozenDomainModel


class Recommendation(FrozenDomainModel):
    """A single actionable recommendation addressing one or more risks."""

    recommendation_id: str = Field(..., description="Unique recommendation identifier.")
    action: RecommendationAction = Field(..., description="Concrete action proposed.")
    addresses_risk_ids: list[str] = Field(
        default_factory=list,
        description="Risk ids this recommendation is intended to mitigate.",
    )
    title: str = Field(..., description="Short human-readable summary.")
    description: str = Field(..., description="Detailed description of the action.")
    target_entities: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Entity ids the action targets, grouped by type.",
    )
    expected_impact: dict[str, Any] = Field(
        default_factory=dict,
        description="Estimated deterministic impact (e.g. minutes recovered).",
    )
    feasibility: RecommendationFeasibility = Field(
        default=RecommendationFeasibility.FEASIBLE,
        description="Feasibility assessment of the action.",
    )
    priority: int = Field(
        default=5, ge=1, le=10, description="Suggested action priority (10 = highest)."
    )


class RecommendationSet(FrozenDomainModel):
    """The full ranked set of recommendations for a production day."""

    business_date: str = Field(..., description="Day the set applies to (YYYY-MM-DD).")
    recommendations: list[Recommendation] = Field(
        default_factory=list, description="All generated recommendations."
    )
