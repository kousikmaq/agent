"""Agent and workflow error hierarchy.

Distinguishes *recoverable* failures (worth retrying) from *critical* failures
(the workflow should stop). Used by the base agent's retry logic and the
orchestrator's failure handling.
"""

from __future__ import annotations


class AgentError(Exception):
    """Base class for errors raised by an agent.

    Attributes
    ----------
    recoverable:
        Whether the orchestrator/base-agent may retry the operation.
    """

    recoverable: bool = False


class RecoverableAgentError(AgentError):
    """A transient failure that may succeed on retry (e.g. missing dataset)."""

    recoverable = True


class CriticalAgentError(AgentError):
    """A non-recoverable failure that must stop the workflow.

    Reserved for cases such as fatal validation errors or an infeasible model.
    """

    recoverable = False


class WorkflowError(Exception):
    """Raised for orchestration-level problems (bad configuration, etc.)."""
