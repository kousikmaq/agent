"""Business Rules Engine.

Deterministically evaluates the active business rules in a factory snapshot and
produces a resolved :class:`~app.rules.policy.RulePolicy`. The engine itself is
generic: it seeds baseline order weights, then dispatches each active rule to
its registered handler in a stable, reproducible order. It performs no
optimization and no scheduling.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain.models.factory_state import FactoryState
from app.rules.definitions import (
    RULE_HANDLERS,
    RuleHandler,
    seed_default_order_weights,
)
from app.rules.policy import RulePolicy, RulePolicyBuilder

logger = get_logger(__name__)


class BusinessRulesEngine:
    """Resolves business rules into a deterministic scheduling policy."""

    def __init__(self, handlers: dict | None = None) -> None:
        """Create the engine.

        Parameters
        ----------
        handlers:
            Optional override of the rule-type -> handler registry (useful for
            testing or custom rule sets). Defaults to :data:`RULE_HANDLERS`.
        """
        self._handlers: dict = handlers if handlers is not None else RULE_HANDLERS

    def evaluate(self, state: FactoryState) -> RulePolicy:
        """Resolve ``state``'s active business rules into a :class:`RulePolicy`."""
        builder = RulePolicyBuilder()

        # 1. Baseline: every order gets a weight from its intrinsic priority.
        seed_default_order_weights(state, builder)

        # 2. Apply active rules in a deterministic order (by rule_id) so the
        #    resolved policy is fully reproducible.
        active_rules = sorted(
            (rule for rule in state.business_rules if rule.is_active),
            key=lambda rule: rule.rule_id,
        )
        for rule in active_rules:
            handler: RuleHandler | None = self._handlers.get(rule.rule_type)
            if handler is None:
                message = (
                    f"No handler registered for rule type {rule.rule_type} "
                    f"(rule {rule.rule_id}); skipped."
                )
                logger.warning(message)
                builder.warnings.append(message)
                continue
            handler(rule, state, builder)
            builder.applied_rule_ids.append(rule.rule_id)

        return builder.build(state.business_date)
