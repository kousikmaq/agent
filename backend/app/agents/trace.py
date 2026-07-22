"""Execution trace models.

Structured, serialisable record of how a workflow run unfolded - one step per
agent - for logging, API responses, and diagnostics.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentStepTrace(BaseModel):
    """The recorded outcome of a single agent execution."""

    agent: str
    status: str
    attempts: int
    duration_ms: float
    started_at: str
    finished_at: str
    error: str | None = None


class ExecutionTrace(BaseModel):
    """The ordered set of agent steps for one workflow run."""

    run_id: str
    business_date: str
    steps: list[AgentStepTrace] = Field(default_factory=list)

    def record(self, step: AgentStepTrace) -> None:
        """Append an agent step to the trace."""
        self.steps.append(step)

    @property
    def total_duration_ms(self) -> float:
        """Sum of all recorded step durations in milliseconds."""
        return round(sum(step.duration_ms for step in self.steps), 3)

    def completed_agents(self) -> list[str]:
        """Names of agents that completed successfully, in order."""
        return [step.agent for step in self.steps if step.status == "SUCCESS"]
