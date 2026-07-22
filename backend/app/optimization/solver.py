"""Scheduling solver - the public entry point to the optimization engine.

Builds the CP-SAT model from a factory snapshot and resolved rule policy, solves
it deterministically (fixed seed + fixed workers), and returns an immutable
:class:`ScheduleResult`. This is the only class the orchestration/API layers
need to use.
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from app.core.logging import get_logger
from app.domain.enums import SolverStatus
from app.domain.models.factory_state import FactoryState
from app.domain.models.schedule import ScheduleResult
from app.optimization.config import SolverOptions
from app.optimization.cp_sat_model import SchedulingModel
from app.optimization.result import build_schedule_result
from app.rules.policy import RulePolicy

logger = get_logger(__name__)


class SchedulingSolver:
    """Deterministically solves the production scheduling problem."""

    def __init__(self, options: SolverOptions | None = None) -> None:
        self._options = options or SolverOptions.from_settings()

    @property
    def options(self) -> SolverOptions:
        """The solver options in effect."""
        return self._options

    def solve(self, state: FactoryState, policy: RulePolicy) -> ScheduleResult:
        """Build and solve the model, returning a :class:`ScheduleResult`."""
        model = SchedulingModel(state, policy, self._options).build()

        if not model.tasks:
            logger.info("No schedulable operations for %s.", state.business_date)
            return ScheduleResult(
                business_date=state.business_date,
                status=SolverStatus.OPTIMAL,
                scheduled_operations=[],
                makespan_minutes=0,
                objective_value=0.0,
                solve_time_seconds=0.0,
            )

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self._options.max_time_seconds
        solver.parameters.random_seed = self._options.random_seed
        solver.parameters.num_search_workers = self._options.num_search_workers

        cp_status = solver.Solve(model.model)
        result = build_schedule_result(model, solver, cp_status)

        for warning in model.warnings:
            logger.warning(warning)
        logger.info(
            "Solved %s: status=%s, operations=%d, makespan=%s, time=%.2fs",
            state.business_date,
            result.status,
            len(result.scheduled_operations),
            result.makespan_minutes,
            result.solve_time_seconds or 0.0,
        )
        return result


def optimize(
    state: FactoryState, policy: RulePolicy, options: SolverOptions | None = None
) -> ScheduleResult:
    """Convenience helper: solve a snapshot with the given policy."""
    return SchedulingSolver(options).solve(state, policy)
