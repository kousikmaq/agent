"""Business rule catalog - one deterministic handler per rule type.

Each handler is a pure function that reads a single
:class:`~app.domain.models.business_rule.BusinessRule` plus the factory snapshot
and mutates the :class:`~app.rules.policy.RulePolicyBuilder`. Handlers contain
no randomness and no optimization - given the same inputs they always produce
the same policy contribution.

New rule types are supported by adding a handler and registering it in
:data:`RULE_HANDLERS` (Open/Closed Principle - the engine never changes).
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.logging import get_logger
from app.domain.enums import BusinessRuleType, RuleEnforcement
from app.domain.models.business_rule import BusinessRule
from app.domain.models.factory_state import FactoryState
from app.rules.policy import RulePolicyBuilder

logger = get_logger(__name__)

# A handler resolves one rule into the policy builder.
RuleHandler = Callable[[BusinessRule, FactoryState, RulePolicyBuilder], None]


def _as_float(value: object, default: float) -> float:
    """Best-effort numeric coercion with a deterministic fallback."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def seed_default_order_weights(state: FactoryState, builder: RulePolicyBuilder) -> None:
    """Initialise every order's weight from its intrinsic priority.

    Establishes a baseline so a schedulable weight always exists even when no
    ``PRIORITY_WEIGHT`` rule is configured.
    """
    for order in state.production_orders:
        builder.order_priority_weights[order.order_id] = float(order.priority)


def apply_priority_weight(
    rule: BusinessRule, state: FactoryState, builder: RulePolicyBuilder
) -> None:
    """Weight orders by ``priority x customer-tier x rule.weight``.

    The rule's ``parameters`` map customer tiers to numeric weights, e.g.
    ``{"STRATEGIC": 4, "KEY": 3, "STANDARD": 2, "LOW": 1}``.
    """
    tier_weights = {str(k): _as_float(v, 1.0) for k, v in rule.parameters.items()}
    tier_by_customer = {c.customer_id: str(c.tier) for c in state.customers}
    global_multiplier = rule.weight or 1.0

    for order in state.production_orders:
        tier = tier_by_customer.get(order.customer_id or "", "")
        tier_weight = tier_weights.get(tier, 1.0)
        builder.order_priority_weights[order.order_id] = (
            float(order.priority) * tier_weight * global_multiplier
        )


def apply_due_date_enforcement(
    rule: BusinessRule, state: FactoryState, builder: RulePolicyBuilder
) -> None:
    """Set the tardiness penalty and whether due dates are hard or soft."""
    builder.due_date_enforcement = rule.enforcement
    builder.tardiness_penalty_per_day = _as_float(
        rule.parameters.get("tardiness_penalty_per_day"),
        builder.tardiness_penalty_per_day,
    )


def apply_max_overtime(
    rule: BusinessRule, state: FactoryState, builder: RulePolicyBuilder
) -> None:
    """Set the plant-wide daily overtime cap (a hard limit)."""
    builder.max_overtime_minutes_per_day = _as_int(
        rule.parameters.get("max_overtime_minutes_per_day"),
        builder.max_overtime_minutes_per_day,
    )


def apply_safety_stock(
    rule: BusinessRule, state: FactoryState, builder: RulePolicyBuilder
) -> None:
    """Toggle whether safety-stock levels must be respected."""
    value = rule.parameters.get("respect_safety_stock", True)
    builder.respect_safety_stock = bool(value)


def apply_setup_minimization(
    rule: BusinessRule, state: FactoryState, builder: RulePolicyBuilder
) -> None:
    """Set the objective weight applied to total setup time."""
    builder.setup_minimization_weight = _as_float(
        rule.parameters.get("weight", rule.weight), builder.setup_minimization_weight
    )


def apply_shift_limit(
    rule: BusinessRule, state: FactoryState, builder: RulePolicyBuilder
) -> None:
    """Set the maximum number of shifts a worker may cover per day."""
    builder.shift_limit_per_worker = _as_int(
        rule.parameters.get("max_shifts_per_worker"),
        builder.shift_limit_per_worker or 1,
    )


def apply_machine_eligibility(
    rule: BusinessRule, state: FactoryState, builder: RulePolicyBuilder
) -> None:
    """Restrict which machines may run specific operations.

    Supported ``parameters`` shapes:

    * ``{"operation_overrides": {"OP-0001": ["MC-0001", "MC-0002"]}}``
    * ``{"work_center": "MACHINING", "allowed_machine_ids": ["MC-0004"]}``
    """
    overrides = rule.parameters.get("operation_overrides")
    if isinstance(overrides, dict):
        for operation_id, machine_ids in overrides.items():
            if isinstance(machine_ids, list):
                builder.machine_eligibility_overrides[str(operation_id)] = [
                    str(m) for m in machine_ids
                ]

    work_center = rule.parameters.get("work_center")
    allowed = rule.parameters.get("allowed_machine_ids")
    if work_center and isinstance(allowed, list):
        allowed_ids = [str(m) for m in allowed]
        for routing in state.routings:
            for operation in routing.operations:
                if operation.work_center == work_center:
                    builder.machine_eligibility_overrides[operation.operation_id] = list(
                        allowed_ids
                    )


# Registry dispatched by the engine. Extend here to support new rule types.
RULE_HANDLERS: dict[BusinessRuleType, RuleHandler] = {
    BusinessRuleType.PRIORITY_WEIGHT: apply_priority_weight,
    BusinessRuleType.DUE_DATE_ENFORCEMENT: apply_due_date_enforcement,
    BusinessRuleType.MAX_OVERTIME: apply_max_overtime,
    BusinessRuleType.SAFETY_STOCK: apply_safety_stock,
    BusinessRuleType.SETUP_MINIMIZATION: apply_setup_minimization,
    BusinessRuleType.SHIFT_LIMIT: apply_shift_limit,
    BusinessRuleType.MACHINE_ELIGIBILITY: apply_machine_eligibility,
}
