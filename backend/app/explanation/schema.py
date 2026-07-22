"""Curated explanation summary schema.

The full :class:`~app.domain.models.explanation.ExplanationContext` bundles every
deterministic output for audit. For the LLM we additionally build a *trimmed*
``ExplanationSummary`` - concise, token-bounded, and grounded - so the assistant
reasons over curated facts rather than raw, unbounded data (e.g. hundreds of
scheduled operations). Nothing here performs scheduling or calls the LLM.
"""

from __future__ import annotations

from typing import Any

from app.domain.models.base import FrozenDomainModel


class ScheduleSummary(FrozenDomainModel):
    """Headline schedule facts (counts, not the full operation list)."""

    status: str
    scheduled_operations: int
    scheduled_orders: int
    makespan_minutes: int | None
    objective_value: float | None
    solve_time_seconds: float | None


class RiskDigest(FrozenDomainModel):
    """A single risk, with the detail needed to explain root causes."""

    risk_id: str
    risk_type: str
    severity: str
    title: str
    description: str = ""
    affected_entities: dict[str, list[str]] = {}
    evidence: dict[str, Any] = {}


class LateOrderDigest(FrozenDomainModel):
    """A late order with its timing, route and the risks driving the delay."""

    order_id: str
    tardiness_minutes: float
    due_date: str | None = None
    scheduled_completion: str | None = None
    machines: list[str] = []
    causes: list[str] = []


class MachineLoadDigest(FrozenDomainModel):
    """How heavily a machine is loaded on the day (from the schedule)."""

    machine_id: str
    scheduled_minutes: int
    operations: int


class MachineTrendDigest(FrozenDomainModel):
    """A machine's scheduled load over recent days (for 'slowing down' Qs)."""

    machine_id: str
    series: list[dict[str, Any]]  # [{"date": "...", "minutes": N, "operations": M}]
    direction: str  # "rising" | "falling" | "flat"


class RiskSummary(FrozenDomainModel):
    """Aggregated risk counts plus the most severe risks."""

    total: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    top: list[RiskDigest]


class RecommendationDigest(FrozenDomainModel):
    """A single recommendation, reduced to its identifying fields."""

    recommendation_id: str
    action: str
    priority: int
    feasibility: str
    title: str
    addresses_risk_ids: list[str]


class RecommendationSummary(FrozenDomainModel):
    """Aggregated recommendation counts plus the highest-priority actions."""

    total: int
    by_action: dict[str, int]
    by_feasibility: dict[str, int]
    top: list[RecommendationDigest]


class ScenarioDigest(FrozenDomainModel):
    """A single scenario's headline KPIs."""

    scenario_type: str
    name: str
    is_baseline: bool
    kpis: dict[str, float]


class ScenarioSummary(FrozenDomainModel):
    """Scenario comparison reduced for explanation."""

    baseline_type: str
    scenarios: list[ScenarioDigest]
    kpi_deltas: dict[str, dict[str, float]]
    best_makespan_scenario: str | None


class ChangeSummary(FrozenDomainModel):
    """What changed versus the prior day (counts by event type)."""

    total: int
    by_type: dict[str, int]
    previous_date: str | None


class ExplanationSummary(FrozenDomainModel):
    """The curated, token-bounded view handed to the LLM."""

    business_date: str
    schedule: ScheduleSummary
    kpis: dict[str, Any]
    risks: RiskSummary
    recommendations: RecommendationSummary
    scenarios: ScenarioSummary
    changes: ChangeSummary | None
    late_orders: list[LateOrderDigest] = []
    machine_load: list[MachineLoadDigest] = []
    machine_trend: list[MachineTrendDigest] = []
