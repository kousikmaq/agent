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
from app.optimization.objective_spec import DEFAULT_WEIGHTS, ObjectiveWeights
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

    def solve(
        self,
        state: FactoryState,
        policy: RulePolicy,
        objective: ObjectiveWeights | None = None,
        warm_start: ScheduleResult | None = None,
    ) -> ScheduleResult:
        """Build and solve the model, returning a :class:`ScheduleResult`.

        ``objective`` is a term-name -> weight mapping (all minimised). Weights
        encode a scenario's priority order — the primary business goal dominates
        the secondary terms — so each scenario pursues its own strategy while a
        single solve always yields a feasible schedule. Defaults to on-time
        delivery, then tardiness, then a light compactness pull.

        ``warm_start`` seeds the solver with an existing schedule (the baseline
        plan). Because the what-if scenarios only *add* resources, the baseline
        assignment is always feasible in them, so warm-starting guarantees a
        scenario never scores worse than the baseline just because its larger
        model is harder to solve in the time budget.
        """
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

        weights = objective or DEFAULT_WEIGHTS
        self._apply_objective(model, weights)
        if warm_start is not None:
            self._apply_warm_start(model, warm_start)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self._options.max_time_seconds
        solver.parameters.random_seed = self._options.random_seed
        solver.parameters.num_search_workers = self._options.num_search_workers

        cp_status = solver.Solve(model.model)
        result = build_schedule_result(model, solver, cp_status)

        for warning in model.warnings:
            logger.warning(warning)
        logger.info(
            "Solved %s [%s]: status=%s, operations=%d, makespan=%s, time=%.2fs",
            state.business_date,
            ",".join(f"{k}:{v}" for k, v in weights.items()),
            result.status,
            len(result.scheduled_operations),
            result.makespan_minutes,
            result.solve_time_seconds or 0.0,
        )
        return result

    @staticmethod
    def _apply_objective(model: SchedulingModel, weights: ObjectiveWeights) -> None:
        """Set a single weighted-sum objective from the published terms."""
        terms = []
        for name, weight in weights.items():
            expr = model.objective_terms.get(name)
            if expr is None or weight == 0:
                continue
            terms.append(weight * expr)
        if terms:
            model.model.Minimize(sum(terms))

    @staticmethod
    def _apply_warm_start(
        model: SchedulingModel, warm_start: ScheduleResult
    ) -> None:
        """Hint the model with a prior schedule's start/machine/worker choices."""
        by_key = {
            (op.order_id, op.operation_id): op
            for op in warm_start.scheduled_operations
        }
        cp = model.model
        for task in model.tasks:
            op = by_key.get(task.key)
            if op is None:
                continue
            start_minute = model.to_minute(op.start)
            if 0 <= start_minute <= model.horizon:
                cp.AddHint(task.start, start_minute)
            presence = task.machine_presence.get(op.machine_id)
            if presence is not None:
                cp.AddHint(presence, 1)
            if op.worker_id is not None:
                wp = task.worker_presence.get(op.worker_id)
                if wp is not None:
                    cp.AddHint(wp, 1)





def optimize(
    state: FactoryState, policy: RulePolicy, options: SolverOptions | None = None
) -> ScheduleResult:
    """Convenience helper: solve a snapshot with the given policy."""
    return SchedulingSolver(options).solve(state, policy)
