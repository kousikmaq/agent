"""Resolved rule policy - the deterministic output of the rules engine.

The rules engine interprets the raw :class:`~app.domain.models.business_rule.BusinessRule`
records in a factory snapshot and distils them into a single, immutable
``RulePolicy``. This policy is the stable contract the optimization engine
consumes later; it contains resolved weights, hard limits, and eligibility
overrides but performs no scheduling itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import RuleEnforcement
from app.domain.models.base import FrozenDomainModel

# Deterministic defaults applied when no governing rule is present.
DEFAULT_TARDINESS_PENALTY_PER_DAY = 100.0
DEFAULT_MAX_OVERTIME_MINUTES = 120
DEFAULT_SETUP_MINIMIZATION_WEIGHT = 0.0
DEFAULT_DUE_DATE_ENFORCEMENT = RuleEnforcement.SOFT
DEFAULT_RESPECT_SAFETY_STOCK = True


class RulePolicy(FrozenDomainModel):
    """Immutable, resolved scheduling policy derived from business rules."""

    business_date: str

    # Per-order weight used to prioritise orders in the objective (higher =
    # more important). Deterministically derived from order priority and
    # customer tier.
    order_priority_weights: dict[str, float]

    # Due-date policy.
    due_date_enforcement: RuleEnforcement = DEFAULT_DUE_DATE_ENFORCEMENT
    tardiness_penalty_per_day: float = DEFAULT_TARDINESS_PENALTY_PER_DAY

    # Labour policy.
    max_overtime_minutes_per_day: int = DEFAULT_MAX_OVERTIME_MINUTES
    shift_limit_per_worker: int | None = None

    # Material policy.
    respect_safety_stock: bool = DEFAULT_RESPECT_SAFETY_STOCK

    # Objective shaping.
    setup_minimization_weight: float = DEFAULT_SETUP_MINIMIZATION_WEIGHT

    # Operation -> allowed machine ids, restricting the routing's eligibility.
    machine_eligibility_overrides: dict[str, list[str]] = {}

    # Provenance / diagnostics.
    applied_rule_ids: list[str] = []
    warnings: list[str] = []


@dataclass
class RulePolicyBuilder:
    """Mutable accumulator that the rule handlers populate.

    Kept separate from the frozen :class:`RulePolicy` so handlers can build the
    policy incrementally, after which :meth:`build` produces the immutable
    result.
    """

    order_priority_weights: dict[str, float] = field(default_factory=dict)
    due_date_enforcement: RuleEnforcement = DEFAULT_DUE_DATE_ENFORCEMENT
    tardiness_penalty_per_day: float = DEFAULT_TARDINESS_PENALTY_PER_DAY
    max_overtime_minutes_per_day: int = DEFAULT_MAX_OVERTIME_MINUTES
    shift_limit_per_worker: int | None = None
    respect_safety_stock: bool = DEFAULT_RESPECT_SAFETY_STOCK
    setup_minimization_weight: float = DEFAULT_SETUP_MINIMIZATION_WEIGHT
    machine_eligibility_overrides: dict[str, list[str]] = field(default_factory=dict)
    applied_rule_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def build(self, business_date: str) -> RulePolicy:
        """Freeze the accumulated state into a :class:`RulePolicy`."""
        return RulePolicy(
            business_date=business_date,
            order_priority_weights=dict(self.order_priority_weights),
            due_date_enforcement=self.due_date_enforcement,
            tardiness_penalty_per_day=self.tardiness_penalty_per_day,
            max_overtime_minutes_per_day=self.max_overtime_minutes_per_day,
            shift_limit_per_worker=self.shift_limit_per_worker,
            respect_safety_stock=self.respect_safety_stock,
            setup_minimization_weight=self.setup_minimization_weight,
            machine_eligibility_overrides=dict(self.machine_eligibility_overrides),
            applied_rule_ids=list(self.applied_rule_ids),
            warnings=list(self.warnings),
        )
