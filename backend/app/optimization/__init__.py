"""OR-Tools CP-SAT optimization engine.

Deterministic constraint-programming scheduler. Consumes a
:class:`~app.domain.models.factory_state.FactoryState` and a resolved
:class:`~app.rules.policy.RulePolicy`, and produces an immutable
:class:`~app.domain.models.schedule.ScheduleResult`. Contains no ML and no LLM.
"""

from __future__ import annotations

from app.optimization.config import SolverOptions
from app.optimization.solver import SchedulingSolver, optimize

__all__ = ["SchedulingSolver", "SolverOptions", "optimize"]
