"""Strongly-typed agent contracts.

Each agent produces one contract that the next agent consumes, mirroring the
deterministic pipeline. Contracts *wrap* the existing domain DTOs (from
``app.domain.models``) and add no business logic. Payload fields are optional so
the Phase-1 skeleton can emit mock contracts without invoking any engine.

Contract flow:
    DataAgentOutput -> ValidationAgentOutput -> PlanningAgentOutput ->
    AnalyticsAgentOutput -> RiskAgentOutput -> RecommendationAgentOutput ->
    ScenarioAgentOutput -> ExplanationAgentOutput
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.timing import utc_now_iso
from app.domain.models.analytics import KpiSet
from app.domain.models.explanation import ExplanationContext
from app.domain.models.factory_state import FactoryState
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import RiskReport
from app.domain.models.scenario import ScenarioComparison
from app.domain.models.schedule import ScheduleResult


class AgentContract(BaseModel):
    """Base contract carried on a workflow edge."""

    agent: str = Field(..., description="Name of the producing agent.")
    business_date: str = Field(..., description="Business date (YYYY-MM-DD).")
    produced_at: str = Field(default_factory=utc_now_iso, description="UTC timestamp.")
    note: str | None = Field(default=None, description="Optional diagnostic note.")


class DataAgentOutput(AgentContract):
    """Data Agent -> loaded factory snapshot."""

    factory_state: FactoryState | None = None


class ValidationAgentOutput(AgentContract):
    """Validation Agent -> validation outcome (workflow stops if not passed)."""

    validation_passed: bool = True
    issues: list[dict[str, Any]] = Field(default_factory=list)


class PlanningAgentOutput(AgentContract):
    """Planning Agent -> optimized schedule (from OR-Tools; never an LLM)."""

    schedule: ScheduleResult | None = None


class AnalyticsAgentOutput(AgentContract):
    """Analytics Agent -> KPIs."""

    kpis: KpiSet | None = None


class RiskAgentOutput(AgentContract):
    """Risk Detection Agent -> risk report."""

    risks: RiskReport | None = None


class RecommendationAgentOutput(AgentContract):
    """Recommendation Agent -> recommendation set."""

    recommendations: RecommendationSet | None = None


class ScenarioAgentOutput(AgentContract):
    """Scenario Planning Agent -> scenario comparison."""

    scenario_comparison: ScenarioComparison | None = None


class ExplanationAgentOutput(AgentContract):
    """Explanation Agent -> explanation context + optional natural-language answer."""

    explanation_context: ExplanationContext | None = None
    answer: str | None = None
