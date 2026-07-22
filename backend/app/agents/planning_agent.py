"""Planning Agent.

A thin wrapper around the existing deterministic scheduling pipeline - no
scheduling logic is duplicated here:
- BusinessRulesEngine (resolves the RulePolicy)
- OR-Tools CP-SAT SchedulingSolver (produces the ScheduleResult)

Reads the FactoryState from the shared context, resolves the policy, solves,
and stores both the RulePolicy and the ScheduleResult back into the context.
Never uses an LLM.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import WorkflowContext
from app.agents.contracts import PlanningAgentOutput
from app.agents.data_agent import FACTORY_STATE_KEY
from app.agents.errors import CriticalAgentError
from app.agents.timing import Stopwatch, utc_now_iso
from app.domain.enums import OrderStatus, SolverStatus
from app.domain.models.factory_state import FactoryState
from app.optimization import SchedulingSolver, SolverOptions
from app.rules import BusinessRulesEngine

# Shared-context keys for the produced artifacts.
RULE_POLICY_KEY = "rule_policy"
SCHEDULE_RESULT_KEY = "schedule_result"

_SCHEDULABLE_STATUSES = {
    OrderStatus.PLANNED,
    OrderStatus.RELEASED,
    OrderStatus.IN_PROGRESS,
}
_SOLVER_FAILURE_STATUSES = {SolverStatus.INFEASIBLE, SolverStatus.MODEL_INVALID}


def _expected_operations(state: FactoryState) -> int:
    """Count the operations expected to be scheduled (counting only)."""
    routing_by_product = {r.product_id: r for r in state.routings}
    total = 0
    for order in state.production_orders:
        if order.status not in _SCHEDULABLE_STATUSES:
            continue
        routing = routing_by_product.get(order.product_id)
        if routing is not None:
            total += len(routing.operations)
    return total


class PlanningAgent(BaseAgent):
    """Produces the optimized schedule via the existing deterministic solver."""

    name = "planning_agent"

    def __init__(
        self,
        options: SolverOptions | None = None,
        solver: SchedulingSolver | None = None,
        rules_engine: BusinessRulesEngine | None = None,
    ) -> None:
        self._options = options or SolverOptions.from_settings()
        self._solver = solver
        self._rules_engine = rules_engine

    def execute(self, context: WorkflowContext) -> PlanningAgentOutput:
        state = context.shared.get(FACTORY_STATE_KEY)
        if state is None:
            raise CriticalAgentError(
                "No FactoryState in context; the Data Agent must run first."
            )

        # 1. Resolve the deterministic rule policy (existing engine).
        rules = self._rules_engine or BusinessRulesEngine()
        policy = rules.evaluate(state)
        context.shared[RULE_POLICY_KEY] = policy

        # 2. Invoke the existing OR-Tools CP-SAT solver.
        solver = self._solver or SchedulingSolver(self._options)
        started_at = utc_now_iso()
        with Stopwatch() as sw:
            schedule = solver.solve(state, policy)
        finished_at = utc_now_iso()

        # Store the schedule (even on failure) for diagnostics/visibility.
        context.shared[SCHEDULE_RESULT_KEY] = schedule

        expected = _expected_operations(state)
        scheduled = len(schedule.scheduled_operations)
        unscheduled = max(0, expected - scheduled)

        self.logger.info(
            "Solver start=%s end=%s duration=%.1f ms | status=%s makespan=%s "
            "scheduled=%d unscheduled=%d constraint_violations=n/a",
            started_at,
            finished_at,
            sw.elapsed_ms,
            schedule.status,
            schedule.makespan_minutes,
            scheduled,
            unscheduled,
        )

        # 3. Stop the workflow on a solver failure, recording diagnostics.
        if schedule.status in _SOLVER_FAILURE_STATUSES:
            self.logger.error(
                "Solver failure: status=%s objective=%s solve_time=%.3fs",
                schedule.status,
                schedule.objective_value,
                schedule.solve_time_seconds or 0.0,
            )
            raise CriticalAgentError(
                f"Solver returned {schedule.status} for {context.business_date}."
            )

        return PlanningAgentOutput(
            agent=self.name,
            business_date=context.business_date,
            schedule=schedule,
        )
