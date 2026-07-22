"""Scenario planning DTOs.

Output structures produced by the Scenario Planning Engine (later phase). Each
scenario is solved deterministically and its KPIs compared against the current
plan baseline.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.enums import ScenarioType
from app.domain.models.base import FrozenDomainModel


class ScenarioDefinition(FrozenDomainModel):
    """Configuration describing how a scenario transforms the factory state."""

    scenario_type: ScenarioType = Field(..., description="Predefined scenario kind.")
    name: str = Field(..., description="Human-readable scenario name.")
    description: str = Field(..., description="What the scenario changes and why.")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Scenario-specific transform parameters.",
    )


class ScenarioResult(FrozenDomainModel):
    """The outcome (KPIs) of solving a single scenario."""

    scenario_type: ScenarioType = Field(..., description="Scenario that was solved.")
    name: str = Field(..., description="Human-readable scenario name.")
    kpis: dict[str, float] = Field(
        default_factory=dict, description="KPI name -> value for this scenario."
    )
    is_baseline: bool = Field(
        default=False, description="True for the current-plan baseline scenario."
    )


class ScenarioComparison(FrozenDomainModel):
    """Side-by-side comparison of all scenarios against the baseline."""

    business_date: str = Field(..., description="Day the comparison applies to (YYYY-MM-DD).")
    baseline_type: ScenarioType = Field(
        default=ScenarioType.CURRENT_PLAN,
        description="Scenario used as the comparison baseline.",
    )
    results: list[ScenarioResult] = Field(
        default_factory=list, description="Per-scenario KPI results."
    )
    kpi_deltas: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Scenario name -> {KPI -> delta vs. baseline}.",
    )
