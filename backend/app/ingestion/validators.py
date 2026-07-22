"""Cross-entity (referential integrity) validation.

Pydantic guarantees each record is *individually* well-formed; these validators
verify the snapshot is *collectively* consistent - every foreign-key-style
reference resolves, and no structurally impossible situations exist (e.g. a
finished good with no routing).

Errors are fatal (the loader refuses the snapshot); warnings are surfaced for
visibility but do not block scheduling.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.domain.models.factory_state import FactoryState


class ValidationSeverity(str, Enum):
    """Severity of a validation finding."""

    ERROR = "ERROR"
    WARNING = "WARNING"


class ValidationIssue(BaseModel):
    """A single referential-integrity finding."""

    severity: ValidationSeverity
    code: str = Field(..., description="Stable machine-readable issue code.")
    message: str = Field(..., description="Human-readable description.")
    entity_type: str = Field(..., description="Entity the issue concerns.")
    entity_id: str | None = Field(default=None, description="Affected entity id.")


class ValidationResult(BaseModel):
    """The collected outcome of validating a :class:`FactoryState`."""

    business_date: str
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Fatal issues that must block scheduling."""
        return [i for i in self.issues if i.severity is ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Non-fatal advisory issues."""
        return [i for i in self.issues if i.severity is ValidationSeverity.WARNING]

    @property
    def has_errors(self) -> bool:
        """Whether any fatal issue was found."""
        return any(i.severity is ValidationSeverity.ERROR for i in self.issues)


class _IssueCollector:
    """Small helper to accumulate issues with minimal boilerplate."""

    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []

    def error(self, code: str, message: str, entity_type: str, entity_id: str | None) -> None:
        self.issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code=code,
                message=message,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )

    def warning(self, code: str, message: str, entity_type: str, entity_id: str | None) -> None:
        self.issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code=code,
                message=message,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )


def validate_factory_state(state: FactoryState) -> ValidationResult:
    """Validate cross-entity referential integrity of ``state``."""
    collector = _IssueCollector()

    product_ids = {p.product_id for p in state.products}
    routing_ids = {r.routing_id for r in state.routings}
    machine_ids = {m.machine_id for m in state.machines}
    worker_ids = {w.worker_id for w in state.workers}
    customer_ids = {c.customer_id for c in state.customers}
    supplier_ids = {s.supplier_id for s in state.suppliers}
    shift_ids = {s.shift_id for s in state.shifts}
    skill_codes = {ws.skill for ws in state.worker_skills}

    _validate_products(state, routing_ids, collector)
    _validate_routings(state, product_ids, machine_ids, skill_codes, collector)
    _validate_orders(state, product_ids, customer_ids, collector)
    _validate_boms(state, product_ids, collector)
    _validate_machine_records(state, machine_ids, collector)
    _validate_worker_records(state, worker_ids, shift_ids, collector)
    _validate_shift_calendars(state, shift_ids, collector)
    _validate_inventory(state, product_ids, collector)
    _validate_procurement(state, product_ids, supplier_ids, collector)

    return ValidationResult(business_date=state.business_date, issues=collector.issues)


# --- Individual validation groups -----------------------------------------
def _validate_products(state: FactoryState, routing_ids: set[str], c: _IssueCollector) -> None:
    for product in state.products:
        if product.is_purchased:
            continue
        if product.routing_id is None:
            c.error(
                "product_missing_routing",
                f"Manufactured product {product.product_id} has no routing.",
                "product",
                product.product_id,
            )
        elif product.routing_id not in routing_ids:
            c.error(
                "product_routing_not_found",
                f"Product {product.product_id} references unknown routing "
                f"{product.routing_id}.",
                "product",
                product.product_id,
            )


def _validate_routings(
    state: FactoryState,
    product_ids: set[str],
    machine_ids: set[str],
    skill_codes: set[str],
    c: _IssueCollector,
) -> None:
    for routing in state.routings:
        if routing.product_id not in product_ids:
            c.error(
                "routing_product_not_found",
                f"Routing {routing.routing_id} references unknown product "
                f"{routing.product_id}.",
                "routing",
                routing.routing_id,
            )
        if not routing.operations:
            c.error(
                "routing_has_no_operations",
                f"Routing {routing.routing_id} has no operations.",
                "routing",
                routing.routing_id,
            )
        for operation in routing.operations:
            if not operation.eligible_machine_ids:
                c.error(
                    "operation_no_eligible_machines",
                    f"Operation {operation.operation_id} has no eligible machines.",
                    "operation",
                    operation.operation_id,
                )
            for machine_id in operation.eligible_machine_ids:
                if machine_id not in machine_ids:
                    c.error(
                        "operation_machine_not_found",
                        f"Operation {operation.operation_id} references unknown "
                        f"machine {machine_id}.",
                        "operation",
                        operation.operation_id,
                    )
            if operation.required_skill and operation.required_skill not in skill_codes:
                c.warning(
                    "operation_skill_unstaffed",
                    f"Operation {operation.operation_id} requires skill "
                    f"{operation.required_skill} held by no worker.",
                    "operation",
                    operation.operation_id,
                )


def _validate_orders(
    state: FactoryState, product_ids: set[str], customer_ids: set[str], c: _IssueCollector
) -> None:
    for order in state.production_orders:
        if order.product_id not in product_ids:
            c.error(
                "order_product_not_found",
                f"Order {order.order_id} references unknown product "
                f"{order.product_id}.",
                "production_order",
                order.order_id,
            )
        if order.customer_id and order.customer_id not in customer_ids:
            c.error(
                "order_customer_not_found",
                f"Order {order.order_id} references unknown customer "
                f"{order.customer_id}.",
                "production_order",
                order.order_id,
            )


def _validate_boms(state: FactoryState, product_ids: set[str], c: _IssueCollector) -> None:
    for line in state.boms:
        if line.parent_product_id not in product_ids:
            c.error(
                "bom_parent_not_found",
                f"BOM references unknown parent product {line.parent_product_id}.",
                "bom",
                line.parent_product_id,
            )
        if line.component_product_id not in product_ids:
            c.error(
                "bom_component_not_found",
                f"BOM references unknown component product "
                f"{line.component_product_id}.",
                "bom",
                line.component_product_id,
            )


def _validate_machine_records(
    state: FactoryState, machine_ids: set[str], c: _IssueCollector
) -> None:
    for window in state.machine_availability:
        if window.machine_id not in machine_ids:
            c.error(
                "availability_machine_not_found",
                f"Availability references unknown machine {window.machine_id}.",
                "machine_availability",
                window.machine_id,
            )
    for window in state.machine_maintenance:
        if window.machine_id not in machine_ids:
            c.error(
                "maintenance_machine_not_found",
                f"Maintenance {window.maintenance_id} references unknown machine "
                f"{window.machine_id}.",
                "machine_maintenance",
                window.maintenance_id,
            )


def _validate_worker_records(
    state: FactoryState, worker_ids: set[str], shift_ids: set[str], c: _IssueCollector
) -> None:
    for skill in state.worker_skills:
        if skill.worker_id not in worker_ids:
            c.error(
                "skill_worker_not_found",
                f"Worker skill references unknown worker {skill.worker_id}.",
                "worker_skill",
                skill.worker_id,
            )
    for availability in state.worker_availability:
        if availability.worker_id not in worker_ids:
            c.error(
                "availability_worker_not_found",
                f"Availability references unknown worker {availability.worker_id}.",
                "worker_availability",
                availability.worker_id,
            )
        if availability.shift_id and availability.shift_id not in shift_ids:
            c.error(
                "availability_shift_not_found",
                f"Worker {availability.worker_id} references unknown shift "
                f"{availability.shift_id}.",
                "worker_availability",
                availability.worker_id,
            )


def _validate_shift_calendars(
    state: FactoryState, shift_ids: set[str], c: _IssueCollector
) -> None:
    for calendar in state.shift_calendars:
        if calendar.shift_id not in shift_ids:
            c.error(
                "shift_calendar_shift_not_found",
                f"Shift calendar references unknown shift {calendar.shift_id}.",
                "shift_calendar",
                calendar.shift_id,
            )


def _validate_inventory(
    state: FactoryState, product_ids: set[str], c: _IssueCollector
) -> None:
    for item in state.inventory:
        if item.product_id not in product_ids:
            c.error(
                "inventory_product_not_found",
                f"Inventory references unknown product {item.product_id}.",
                "inventory",
                item.product_id,
            )


def _validate_procurement(
    state: FactoryState, product_ids: set[str], supplier_ids: set[str], c: _IssueCollector
) -> None:
    for po in state.purchase_orders:
        if po.product_id not in product_ids:
            c.error(
                "po_product_not_found",
                f"Purchase order {po.po_id} references unknown product "
                f"{po.product_id}.",
                "purchase_order",
                po.po_id,
            )
        if po.supplier_id not in supplier_ids:
            c.error(
                "po_supplier_not_found",
                f"Purchase order {po.po_id} references unknown supplier "
                f"{po.supplier_id}.",
                "purchase_order",
                po.po_id,
            )
