"""Scenario Planning Engine.

Clones the factory state, applies scenario transforms (overtime, alternate
machines, additional shift), re-runs the CP-SAT solver, and compares KPIs
against the current-plan baseline. Deterministic; no ML, no LLM.
"""

from __future__ import annotations

from app.scenario.definitions import DEFAULT_SCENARIOS, ScenarioSpec
from app.scenario.engine import ScenarioPlanningEngine

__all__ = ["ScenarioPlanningEngine", "DEFAULT_SCENARIOS", "ScenarioSpec"]
