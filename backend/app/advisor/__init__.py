"""LLM planning advisor (goal -> weights, comparison -> recommendation).

A thin, grounded layer *around* the CP-SAT solver: it translates planner intent
into solver inputs and turns solved results into recommendations, but never
produces a schedule itself. The solver stays the single source of every plan, so
feasibility, determinism and auditability are untouched.
"""

from __future__ import annotations

from app.advisor.goal_advisor import PlanningGoalAdvisor
from app.advisor.models import ScenarioRecommendation, WeightProposal
from app.advisor.scenario_advisor import ScenarioAdvisor

__all__ = [
    "PlanningGoalAdvisor",
    "ScenarioAdvisor",
    "ScenarioRecommendation",
    "WeightProposal",
]
