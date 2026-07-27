"""Per-scenario weighted objectives.

Each scenario optimises its OWN objective — a weighted sum of named terms whose
weights encode a priority order (the primary business goal is weighted to
dominate the secondary ones). This gives every scenario a distinct strategy
while doing a single robust solve that always yields a feasible schedule
(strict lexicographic passes repeatedly failed to find a feasible solution
within the per-level time budget on the larger transformed models).

All terms are *minimisation* targets published by
:meth:`app.optimization.cp_sat_model.SchedulingModel._build_objective_terms`.
Maximising on-time delivery is expressed as minimising ``num_late``.
"""

from __future__ import annotations

from app.domain.enums import ScenarioType

# Objective term names (must match SchedulingModel.objective_terms keys).
NUM_LATE = "num_late"
TOTAL_TARDINESS = "total_tardiness"
MAKESPAN = "makespan"
TOTAL_FLOW = "total_flow"  # sum of order completions — compactness / idle proxy
MAX_MACHINE_LOAD = "max_machine_load"  # busiest machine — balance / bottleneck
TOTAL_OVERTIME = "total_overtime"  # cost proxy

# One late order outweighs any tardiness/makespan trade-off, so on-time delivery
# dominates for the delivery-focused scenarios.
_OTD = 2_000_000

# A weighted objective is term-name -> integer weight (all minimised).
ObjectiveWeights = dict[str, int]

# Distinct, purpose-built objective per scenario.
#
# * CURRENT_PLAN     — throughput baseline: minimise makespan and keep orders
#                      from running needlessly late, with only a weak on-time
#                      pull, so it reads as the baseline.
# * OVERTIME_ENABLED — on-time first, then cut tardiness, then MINIMISE overtime
#                      (so overtime is only spent when it reduced lateness).
# * ALTERNATE_MACHINES — on-time first, then relieve the bottleneck / balance.
# * ADDITIONAL_SHIFT — on-time first, then compress makespan, then limit cost.
SCENARIO_WEIGHTS: dict[ScenarioType, ObjectiveWeights] = {
    ScenarioType.CURRENT_PLAN: {
        NUM_LATE: 1_000,
        TOTAL_TARDINESS: 20,
        MAKESPAN: 30,
        MAX_MACHINE_LOAD: 5,
    },
    ScenarioType.OVERTIME_ENABLED: {
        NUM_LATE: _OTD,
        TOTAL_TARDINESS: 50,
        MAKESPAN: 20,
        TOTAL_OVERTIME: 2,
    },
    ScenarioType.ALTERNATE_MACHINES: {
        NUM_LATE: _OTD,
        MAX_MACHINE_LOAD: 200,
        TOTAL_TARDINESS: 20,
        MAKESPAN: 10,
    },
    ScenarioType.ADDITIONAL_SHIFT: {
        NUM_LATE: _OTD,
        TOTAL_TARDINESS: 50,
        MAKESPAN: 60,
        TOTAL_OVERTIME: 2,
    },
}

# Used for ad-hoc solves and mitigation re-plans: on-time delivery, then
# tardiness, with a light compactness pull.
DEFAULT_WEIGHTS: ObjectiveWeights = {
    NUM_LATE: _OTD,
    TOTAL_TARDINESS: 10,
    MAKESPAN: 1,
}


def weights_for(scenario_type: ScenarioType | None) -> ObjectiveWeights:
    """Return the weighted objective for a scenario (or the default)."""
    if scenario_type is None:
        return DEFAULT_WEIGHTS
    return SCENARIO_WEIGHTS.get(scenario_type, DEFAULT_WEIGHTS)
