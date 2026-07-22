"""Base agent.

Provides the common execution envelope for every agent: timing, retry of
recoverable failures, trace recording, and logging. Subclasses implement only
:meth:`execute`, which delegates to an existing engine (in later phases) and
returns a typed contract. The base class contains no business logic.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel

from app.agents.contracts import AgentContract
from app.agents.context import WorkflowContext
from app.agents.errors import AgentError
from app.agents.logging import get_agent_logger
from app.agents.retry import RetryPolicy
from app.agents.timing import Stopwatch, utc_now_iso
from app.agents.trace import AgentStepTrace


class AgentStatus(str, Enum):
    """Outcome of a single agent execution."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AgentResult(BaseModel):
    """Summary of an agent execution (details of the output live in context)."""

    agent: str
    status: AgentStatus
    attempts: int
    duration_ms: float
    error: str | None = None


class BaseAgent(ABC):
    """Abstract base for all workflow agents."""

    #: Unique agent name; subclasses must override.
    name: str = "agent"

    @property
    def logger(self) -> logging.Logger:
        """Logger scoped to this agent."""
        return get_agent_logger(self.name)

    @abstractmethod
    def execute(self, context: WorkflowContext) -> AgentContract:
        """Perform the agent's work and return its output contract.

        Implementations delegate to an existing engine (later phases) and must
        raise :class:`~app.agents.errors.RecoverableAgentError` for transient
        failures or :class:`~app.agents.errors.CriticalAgentError` for fatal
        ones. Phase-1 wrappers return a mock contract.
        """
        raise NotImplementedError

    def run(self, context: WorkflowContext, retry: RetryPolicy) -> AgentResult:
        """Execute the agent with timing, retry, and trace recording."""
        started_at = utc_now_iso()
        attempts = 0
        error: str | None = None
        status = AgentStatus.FAILED

        with Stopwatch() as sw:
            while attempts < retry.max_attempts:
                attempts += 1
                try:
                    output = self.execute(context)
                    context.set_output(self.name, output)
                    status = AgentStatus.SUCCESS
                    error = None
                    break
                except AgentError as exc:
                    error = str(exc)
                    if exc.recoverable and attempts < retry.max_attempts:
                        self.logger.warning(
                            "Recoverable failure (attempt %d/%d): %s",
                            attempts,
                            retry.max_attempts,
                            error,
                        )
                        retry.sleep(retry.next_delay(attempts))
                        continue
                    self.logger.error("Agent failed: %s", error)
                    break
                except Exception as exc:  # noqa: BLE001 - record and stop
                    error = str(exc)
                    self.logger.exception("Unexpected agent error: %s", error)
                    break

        step = AgentStepTrace(
            agent=self.name,
            status=status.value,
            attempts=attempts,
            duration_ms=sw.elapsed_ms,
            started_at=started_at,
            finished_at=utc_now_iso(),
            error=error,
        )
        context.trace.record(step)
        if status is AgentStatus.SUCCESS:
            self.logger.info("Completed in %.1f ms (attempt %d).", sw.elapsed_ms, attempts)

        return AgentResult(
            agent=self.name,
            status=status,
            attempts=attempts,
            duration_ms=sw.elapsed_ms,
            error=error,
        )
