"""Solution extraction: CP-SAT solver output -> ScheduleResult.

Translates a solved :class:`SchedulingModel` into the immutable domain
:class:`~app.domain.models.schedule.ScheduleResult`, converting integer minutes
back into absolute datetimes and reading the chosen machine/worker for each
task.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from ortools.sat.python import cp_model

from app.domain.enums import SolverStatus
from app.domain.models.schedule import ScheduledOperation, ScheduleResult

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel

# Map CP-SAT status codes to the domain solver-status enum.
_STATUS_MAP = {
    cp_model.OPTIMAL: SolverStatus.OPTIMAL,
    cp_model.FEASIBLE: SolverStatus.FEASIBLE,
    cp_model.INFEASIBLE: SolverStatus.INFEASIBLE,
    cp_model.MODEL_INVALID: SolverStatus.MODEL_INVALID,
    cp_model.UNKNOWN: SolverStatus.UNKNOWN,
}


def to_solver_status(cp_status: int) -> SolverStatus:
    """Translate a CP-SAT status code to :class:`SolverStatus`."""
    return _STATUS_MAP.get(cp_status, SolverStatus.UNKNOWN)


def _chosen(presence: dict[str, cp_model.IntVar], solver: cp_model.CpSolver) -> str | None:
    """Return the id whose presence literal is true, if any."""
    for entity_id, literal in presence.items():
        if solver.Value(literal) == 1:
            return entity_id
    return None


def build_schedule_result(
    model: "SchedulingModel", solver: cp_model.CpSolver, cp_status: int
) -> ScheduleResult:
    """Assemble a :class:`ScheduleResult` from a solved model."""
    status = to_solver_status(cp_status)
    solved = cp_status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    scheduled: list[ScheduledOperation] = []
    if solved:
        for task in model.tasks:
            machine_id = _chosen(task.machine_presence, solver)
            worker_id = _chosen(task.worker_presence, solver)
            start_minute = solver.Value(task.start)
            end_minute = solver.Value(task.end)
            scheduled.append(
                ScheduledOperation(
                    order_id=task.order.order_id,
                    operation_id=task.operation.operation_id,
                    machine_id=machine_id or "UNASSIGNED",
                    worker_id=worker_id,
                    start=model.base + timedelta(minutes=start_minute),
                    end=model.base + timedelta(minutes=end_minute),
                )
            )
        scheduled.sort(key=lambda op: (op.start, op.machine_id))

    makespan = (
        solver.Value(model.makespan)
        if solved and model.makespan is not None
        else None
    )
    objective = solver.ObjectiveValue() if solved and model.tasks else None

    return ScheduleResult(
        business_date=model.state.business_date,
        status=status,
        scheduled_operations=scheduled,
        makespan_minutes=makespan,
        objective_value=objective,
        solve_time_seconds=round(solver.WallTime(), 3),
    )
