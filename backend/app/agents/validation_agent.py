"""Validation Agent.

Invokes the existing validation pipeline (schema validation happens during load;
this agent runs the existing cross-entity/business validators) and returns the
existing :class:`ValidationResult`. Stores the result in the shared context and
stops the workflow when critical (fatal) validation errors are present.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import WorkflowContext
from app.agents.contracts import ValidationAgentOutput
from app.agents.data_agent import FACTORY_STATE_KEY
from app.agents.errors import CriticalAgentError
from app.agents.timing import Stopwatch
from app.ingestion import validate_factory_state

# Shared-context key for the produced validation result.
VALIDATION_RESULT_KEY = "validation_result"


class ValidationAgent(BaseAgent):
    """Validates the factory snapshot before planning proceeds."""

    name = "validation_agent"

    def execute(self, context: WorkflowContext) -> ValidationAgentOutput:
        state = context.shared.get(FACTORY_STATE_KEY)
        if state is None:
            raise CriticalAgentError(
                "No FactoryState in context; the Data Agent must run first."
            )

        with Stopwatch() as sw:
            result = validate_factory_state(state)

        # Store the existing ValidationResult for downstream visibility.
        context.shared[VALIDATION_RESULT_KEY] = result

        self.logger.info(
            "Validated in %.1f ms | errors=%d warnings=%d",
            sw.elapsed_ms,
            len(result.errors),
            len(result.warnings),
        )

        if result.has_errors:
            # Result is already stored; stop the workflow on critical failure.
            raise CriticalAgentError(
                f"Validation failed with {len(result.errors)} error(s)."
            )

        return ValidationAgentOutput(
            agent=self.name,
            business_date=context.business_date,
            validation_passed=True,
            issues=[issue.model_dump() for issue in result.warnings],
        )
