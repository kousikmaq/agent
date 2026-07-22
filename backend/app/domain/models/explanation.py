"""ExplanationContext - the sole structured input passed to the LLM.

Assembled by the Explanation Context Builder (later phase) from the outputs of
Optimization, Analytics, Risk Detection, Recommendation, and Scenario Planning.
The chat service consumes only this object; the LLM can never reach the solver
or make scheduling decisions.
"""

from __future__ import annotations

from pydantic import Field

from app.domain.models.analytics import KpiSet
from app.domain.models.base import FrozenDomainModel
from app.domain.models.change_log import ChangeLog
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import RiskReport
from app.domain.models.scenario import ScenarioComparison
from app.domain.models.schedule import ScheduleResult


class ExplanationContext(FrozenDomainModel):
    """Curated, read-only bundle of deterministic outputs for the LLM.

    Every field is a structured DTO produced by an upstream deterministic
    engine. The context is persisted per day for full auditability of exactly
    what the assistant was grounded on.
    """

    business_date: str = Field(..., description="Day the context applies to (YYYY-MM-DD).")
    schedule: ScheduleResult = Field(..., description="Generated schedule summary.")
    kpis: KpiSet = Field(..., description="Computed KPIs.")
    risks: RiskReport = Field(..., description="Detected operational risks.")
    recommendations: RecommendationSet = Field(
        ..., description="Generated corrective recommendations."
    )
    scenario_comparison: ScenarioComparison = Field(
        ..., description="Scenario KPI comparison."
    )
    change_log: ChangeLog | None = Field(
        default=None, description="What changed versus the prior day."
    )
