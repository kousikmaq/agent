"""Shared workflow context and state.

``WorkflowContext`` is the mutable, shared state threaded through the workflow.
Agents read the previous agent's contract from ``outputs`` and write their own;
``shared`` holds cross-cutting state (e.g. FactoryState, RulePolicy in later
phases) so distant agents need no direct dependency on one another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.agents.contracts import AgentContract
from app.agents.trace import ExecutionTrace


class WorkflowState(str, Enum):
    """Lifecycle state of a workflow run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"  # reserved for future HITL gates
    CANCELLED = "CANCELLED"


@dataclass
class WorkflowContext:
    """Mutable state shared across the agents of a single workflow run."""

    run_id: str
    business_date: str
    params: dict[str, Any] = field(default_factory=dict)
    state: WorkflowState = WorkflowState.PENDING
    outputs: dict[str, AgentContract] = field(default_factory=dict)
    shared: dict[str, Any] = field(default_factory=dict)
    trace: ExecutionTrace = field(init=False)

    # --- Human-in-the-loop / resumability ---
    # Index of the next agent to run (enables pause/resume without re-running
    # completed agents).
    next_index: int = 0
    # Approvals recorded per gate (agent name -> approved).
    approvals: dict[str, bool] = field(default_factory=dict)
    # The gate the workflow is currently paused at, if any.
    pending_gate: str | None = None

    def __post_init__(self) -> None:
        self.trace = ExecutionTrace(
            run_id=self.run_id, business_date=self.business_date
        )

    # -- Convenience accessors ---------------------------------------------
    def set_output(self, agent: str, output: AgentContract) -> None:
        """Store an agent's output contract."""
        self.outputs[agent] = output

    def get_output(self, agent: str) -> AgentContract | None:
        """Return a previously produced agent output, if any."""
        return self.outputs.get(agent)
