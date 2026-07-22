"""Workflow skeleton.

An :class:`AgentWorkflow` is the ordered set of agents the orchestrator runs -
the MAF workflow graph rendered as a linear pipeline for the deterministic
planning sequence. It holds no execution logic itself.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.errors import WorkflowError


class AgentWorkflow:
    """An ordered pipeline of agents."""

    def __init__(self, name: str, agents: list[BaseAgent]) -> None:
        if not agents:
            raise WorkflowError("A workflow must contain at least one agent.")
        names = [a.name for a in agents]
        if len(names) != len(set(names)):
            raise WorkflowError("Agent names within a workflow must be unique.")
        self._name = name
        self._agents = list(agents)

    @property
    def name(self) -> str:
        """The workflow's name."""
        return self._name

    @property
    def agents(self) -> list[BaseAgent]:
        """The agents in execution order."""
        return list(self._agents)

    def describe(self) -> list[str]:
        """Return the ordered agent names (for logging / introspection)."""
        return [a.name for a in self._agents]
