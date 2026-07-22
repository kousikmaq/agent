"""Phase 2 tests: domain model validation and interface contracts.

These tests exercise the domain layer in isolation - no services, I/O, or
business logic - verifying construction, validators, and serialization.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest
from pydantic import ValidationError

from app.domain.enums import (
    MaintenanceType,
    OrderStatus,
    RiskSeverity,
    RiskType,
)
from app.domain.interfaces import DataSource
from app.domain.models import (
    BomLine,
    FactoryState,
    InventoryItem,
    MachineMaintenance,
    Operation,
    ProductionOrder,
    PurchaseOrder,
    Risk,
    Routing,
)


def test_production_order_valid_construction() -> None:
    order = ProductionOrder(
        order_id="PO-1",
        product_id="P-1",
        quantity=100,
        release_date=date(2026, 7, 17),
        due_date=date(2026, 7, 20),
    )
    assert order.status is OrderStatus.RELEASED
    assert order.priority == 5


def test_production_order_rejects_due_before_release() -> None:
    with pytest.raises(ValidationError):
        ProductionOrder(
            order_id="PO-2",
            product_id="P-1",
            quantity=10,
            release_date=date(2026, 7, 20),
            due_date=date(2026, 7, 17),
        )


def test_production_order_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValidationError):
        ProductionOrder(
            order_id="PO-3",
            product_id="P-1",
            quantity=0,
            release_date=date(2026, 7, 17),
            due_date=date(2026, 7, 20),
        )


def test_routing_sorts_and_validates_unique_sequences() -> None:
    routing = Routing(
        routing_id="R-1",
        product_id="P-1",
        operations=[
            Operation(
                operation_id="O-2",
                routing_id="R-1",
                sequence=2,
                name="Assemble",
                work_center="WC-A",
                run_minutes_per_unit=1.5,
            ),
            Operation(
                operation_id="O-1",
                routing_id="R-1",
                sequence=1,
                name="Cut",
                work_center="WC-C",
                run_minutes_per_unit=2.0,
                eligible_machine_ids=["M-1", "M-1", "M-2"],
            ),
        ],
    )
    # Sorted by sequence, and duplicate machine ids removed.
    assert [op.operation_id for op in routing.operations] == ["O-1", "O-2"]
    assert routing.operations[0].eligible_machine_ids == ["M-1", "M-2"]


def test_routing_rejects_duplicate_sequence() -> None:
    with pytest.raises(ValidationError):
        Routing(
            routing_id="R-2",
            product_id="P-1",
            operations=[
                Operation(
                    operation_id="O-1",
                    routing_id="R-2",
                    sequence=1,
                    name="A",
                    work_center="WC",
                    run_minutes_per_unit=1.0,
                ),
                Operation(
                    operation_id="O-2",
                    routing_id="R-2",
                    sequence=1,
                    name="B",
                    work_center="WC",
                    run_minutes_per_unit=1.0,
                ),
            ],
        )


def test_maintenance_window_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        MachineMaintenance(
            maintenance_id="MT-1",
            machine_id="M-1",
            maintenance_type=MaintenanceType.PLANNED,
            start=datetime(2026, 7, 17, 10, 0),
            end=datetime(2026, 7, 17, 9, 0),
        )


def test_inventory_allocation_cannot_exceed_on_hand() -> None:
    with pytest.raises(ValidationError):
        InventoryItem(product_id="P-1", on_hand=5, allocated=10)


def test_bom_line_rejects_self_reference() -> None:
    with pytest.raises(ValidationError):
        BomLine(parent_product_id="P-1", component_product_id="P-1", quantity_per=1)


def test_purchase_order_arrival_not_before_order_date() -> None:
    with pytest.raises(ValidationError):
        PurchaseOrder(
            po_id="PUR-1",
            supplier_id="S-1",
            product_id="P-1",
            quantity=100,
            order_date=date(2026, 7, 17),
            expected_arrival=date(2026, 7, 15),
        )


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        InventoryItem(product_id="P-1", on_hand=5, unknown_field=1)  # type: ignore[call-arg]


def test_risk_record_is_immutable() -> None:
    risk = Risk(
        risk_id="RISK-1",
        risk_type=RiskType.DELAYED_ORDER,
        severity=RiskSeverity.HIGH,
        title="Order late",
        description="Order will miss its due date.",
    )
    with pytest.raises(ValidationError):
        risk.severity = RiskSeverity.LOW  # frozen model


def test_empty_factory_state_constructs() -> None:
    state = FactoryState(business_date="2026-07-17")
    assert state.production_orders == []
    assert state.machines == []


def test_datasource_protocol_is_runtime_checkable() -> None:
    class _Dummy:
        def load(self, business_date: str):  # pragma: no cover - structural only
            return FactoryState(business_date=business_date)

        def available_dates(self):  # pragma: no cover - structural only
            return []

    assert isinstance(_Dummy(), DataSource)
