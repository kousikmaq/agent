"""Phase 5 tests: the deterministic business rules engine."""

from __future__ import annotations

from datetime import date

from app.domain.enums import (
    BusinessRuleType,
    CustomerTier,
    OrderStatus,
    RuleEnforcement,
)
from app.domain.models.business_rule import BusinessRule
from app.domain.models.customer import Customer
from app.domain.models.factory_state import FactoryState
from app.domain.models.production_order import ProductionOrder
from app.rules import BusinessRulesEngine
from app.rules.policy import (
    DEFAULT_MAX_OVERTIME_MINUTES,
    DEFAULT_TARDINESS_PENALTY_PER_DAY,
)


def _order(order_id: str, priority: int, customer_id: str | None = None) -> ProductionOrder:
    return ProductionOrder(
        order_id=order_id,
        product_id="P-1",
        customer_id=customer_id,
        quantity=10,
        release_date=date(2026, 7, 17),
        due_date=date(2026, 7, 25),
        priority=priority,
        status=OrderStatus.RELEASED,
    )


def _state(**overrides) -> FactoryState:
    base = dict(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", 5)],
        customers=[],
        business_rules=[],
    )
    base.update(overrides)
    return FactoryState(**base)


def test_defaults_applied_without_rules() -> None:
    policy = BusinessRulesEngine().evaluate(_state())
    assert policy.max_overtime_minutes_per_day == DEFAULT_MAX_OVERTIME_MINUTES
    assert policy.tardiness_penalty_per_day == DEFAULT_TARDINESS_PENALTY_PER_DAY
    assert policy.respect_safety_stock is True
    # Baseline weight equals intrinsic priority.
    assert policy.order_priority_weights["ORD-1"] == 5.0
    assert policy.applied_rule_ids == []


def test_priority_weight_uses_customer_tier() -> None:
    state = _state(
        production_orders=[
            _order("ORD-A", 5, "CU-STRAT"),
            _order("ORD-B", 5, "CU-LOW"),
        ],
        customers=[
            Customer(customer_id="CU-STRAT", name="A", tier=CustomerTier.STRATEGIC),
            Customer(customer_id="CU-LOW", name="B", tier=CustomerTier.LOW),
        ],
        business_rules=[
            BusinessRule(
                rule_id="BR-1",
                rule_type=BusinessRuleType.PRIORITY_WEIGHT,
                enforcement=RuleEnforcement.SOFT,
                weight=2.0,
                parameters={"STRATEGIC": 4, "KEY": 3, "STANDARD": 2, "LOW": 1},
            )
        ],
    )
    policy = BusinessRulesEngine().evaluate(state)
    # 5 * 4 * 2.0 = 40 vs 5 * 1 * 2.0 = 10
    assert policy.order_priority_weights["ORD-A"] == 40.0
    assert policy.order_priority_weights["ORD-B"] == 10.0
    assert "BR-1" in policy.applied_rule_ids


def test_due_date_and_overtime_and_safety_stock_rules() -> None:
    state = _state(
        business_rules=[
            BusinessRule(
                rule_id="BR-DD",
                rule_type=BusinessRuleType.DUE_DATE_ENFORCEMENT,
                enforcement=RuleEnforcement.HARD,
                parameters={"tardiness_penalty_per_day": 250},
            ),
            BusinessRule(
                rule_id="BR-OT",
                rule_type=BusinessRuleType.MAX_OVERTIME,
                enforcement=RuleEnforcement.HARD,
                parameters={"max_overtime_minutes_per_day": 60},
            ),
            BusinessRule(
                rule_id="BR-SS",
                rule_type=BusinessRuleType.SAFETY_STOCK,
                enforcement=RuleEnforcement.HARD,
                parameters={"respect_safety_stock": False},
            ),
        ]
    )
    policy = BusinessRulesEngine().evaluate(state)
    assert policy.due_date_enforcement is RuleEnforcement.HARD
    assert policy.tardiness_penalty_per_day == 250.0
    assert policy.max_overtime_minutes_per_day == 60
    assert policy.respect_safety_stock is False


def test_inactive_rules_are_ignored() -> None:
    state = _state(
        business_rules=[
            BusinessRule(
                rule_id="BR-OT",
                rule_type=BusinessRuleType.MAX_OVERTIME,
                enforcement=RuleEnforcement.HARD,
                parameters={"max_overtime_minutes_per_day": 999},
                is_active=False,
            )
        ]
    )
    policy = BusinessRulesEngine().evaluate(state)
    assert policy.max_overtime_minutes_per_day == DEFAULT_MAX_OVERTIME_MINUTES
    assert "BR-OT" not in policy.applied_rule_ids


def test_unknown_rule_type_records_warning() -> None:
    # A registry that knows no handlers forces the "unhandled" path.
    engine = BusinessRulesEngine(handlers={})
    state = _state(
        business_rules=[
            BusinessRule(
                rule_id="BR-X",
                rule_type=BusinessRuleType.MAX_OVERTIME,
                enforcement=RuleEnforcement.HARD,
                parameters={},
            )
        ]
    )
    policy = engine.evaluate(state)
    assert policy.warnings
    assert "BR-X" not in policy.applied_rule_ids


def test_evaluation_is_deterministic() -> None:
    state = _state(
        business_rules=[
            BusinessRule(
                rule_id="BR-OT",
                rule_type=BusinessRuleType.MAX_OVERTIME,
                enforcement=RuleEnforcement.HARD,
                parameters={"max_overtime_minutes_per_day": 90},
            ),
        ]
    )
    a = BusinessRulesEngine().evaluate(state)
    b = BusinessRulesEngine().evaluate(state)
    assert a.model_dump() == b.model_dump()


def test_machine_eligibility_override_by_work_center() -> None:
    from app.domain.models.routing import Operation, Routing

    routing = Routing(
        routing_id="RT-1",
        product_id="P-1",
        operations=[
            Operation(
                operation_id="OP-1",
                routing_id="RT-1",
                sequence=1,
                name="Mill",
                work_center="MACHINING",
                run_minutes_per_unit=1.0,
                eligible_machine_ids=["MC-1", "MC-2", "MC-3"],
            )
        ],
    )
    state = _state(
        routings=[routing],
        business_rules=[
            BusinessRule(
                rule_id="BR-ME",
                rule_type=BusinessRuleType.MACHINE_ELIGIBILITY,
                enforcement=RuleEnforcement.HARD,
                parameters={"work_center": "MACHINING", "allowed_machine_ids": ["MC-2"]},
            )
        ],
    )
    policy = BusinessRulesEngine().evaluate(state)
    assert policy.machine_eligibility_overrides["OP-1"] == ["MC-2"]
