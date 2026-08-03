"""Objective-term allow-list for the planning advisor.

The advisor may only ever weight these six named terms (the exact set published
by :meth:`app.optimization.cp_sat_model.SchedulingModel._build_objective_terms`
and consumed by :mod:`app.optimization.objective_spec`). Centralising the list
here keeps the LLM prompt, the output validator and the solver in lock-step: a
weight over any name not in this map is dropped, so the model can never steer the
solver with an unknown or malformed term.
"""

from __future__ import annotations

from app.optimization.objective_spec import (
    MAKESPAN,
    MAX_MACHINE_LOAD,
    NUM_LATE,
    TOTAL_FLOW,
    TOTAL_OVERTIME,
    TOTAL_TARDINESS,
)

# Largest weight the advisor may assign to a single term (matches the on-time
# dominance weight used by the built-in scenarios).
WEIGHT_MAX = 2_000_000

# term name -> planner-facing description used in the prompt.
OBJECTIVE_TERMS: dict[str, str] = {
    NUM_LATE: "number of orders finishing after their due date (on-time delivery)",
    TOTAL_TARDINESS: "total minutes late across all orders",
    MAKESPAN: "when the last operation finishes (throughput / speed)",
    TOTAL_FLOW: "sum of order completion times (compactness / less idle)",
    MAX_MACHINE_LOAD: "busiest machine's load (balance / relieve the bottleneck)",
    TOTAL_OVERTIME: "worker-minutes beyond regular capacity (cost proxy)",
}

ALLOWED_TERMS: frozenset[str] = frozenset(OBJECTIVE_TERMS)
