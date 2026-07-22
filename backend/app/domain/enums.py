"""Enumerations shared across the domain layer.

Centralising enums keeps entity definitions terse and guarantees that every
module (ingestion, optimization, risk, recommendation, scenario, explanation)
speaks the same vocabulary. String-valued enums are used throughout so values
round-trip cleanly through CSV/JSON.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-backed enum whose members serialise as their value."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


# ---------------------------------------------------------------------------
# Units & general
# ---------------------------------------------------------------------------
class UnitOfMeasure(StrEnum):
    """Unit of measure for products and materials."""

    EACH = "EACH"
    KILOGRAM = "KG"
    LITER = "L"
    METER = "M"
    HOUR = "HR"


# ---------------------------------------------------------------------------
# Production orders
# ---------------------------------------------------------------------------
class OrderStatus(StrEnum):
    """Lifecycle status of a production order."""

    PLANNED = "PLANNED"
    RELEASED = "RELEASED"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
class CustomerTier(StrEnum):
    """Customer priority tier used for order weighting."""

    STRATEGIC = "STRATEGIC"
    KEY = "KEY"
    STANDARD = "STANDARD"
    LOW = "LOW"


# ---------------------------------------------------------------------------
# Machines & maintenance
# ---------------------------------------------------------------------------
class MachineStatus(StrEnum):
    """Operational status of a machine."""

    AVAILABLE = "AVAILABLE"
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    DOWN = "DOWN"
    MAINTENANCE = "MAINTENANCE"


class MaintenanceType(StrEnum):
    """Classification of a maintenance window."""

    PLANNED = "PLANNED"
    PREVENTIVE = "PREVENTIVE"
    CORRECTIVE = "CORRECTIVE"
    BREAKDOWN = "BREAKDOWN"


# ---------------------------------------------------------------------------
# Workforce & shifts
# ---------------------------------------------------------------------------
class SkillProficiency(StrEnum):
    """Proficiency level a worker holds for a given skill."""

    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    EXPERT = "EXPERT"


class ShiftType(StrEnum):
    """Standard plant shift windows."""

    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    NIGHT = "NIGHT"


class WorkerAvailabilityStatus(StrEnum):
    """Daily availability status of a worker."""

    AVAILABLE = "AVAILABLE"
    ON_LEAVE = "ON_LEAVE"
    SICK = "SICK"
    TRAINING = "TRAINING"


# ---------------------------------------------------------------------------
# Procurement
# ---------------------------------------------------------------------------
class PurchaseOrderStatus(StrEnum):
    """Lifecycle status of a purchase order."""

    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    IN_TRANSIT = "IN_TRANSIT"
    DELAYED = "DELAYED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------
class BusinessRuleType(StrEnum):
    """Category of a configurable business rule."""

    PRIORITY_WEIGHT = "PRIORITY_WEIGHT"
    MAX_OVERTIME = "MAX_OVERTIME"
    MACHINE_ELIGIBILITY = "MACHINE_ELIGIBILITY"
    DUE_DATE_ENFORCEMENT = "DUE_DATE_ENFORCEMENT"
    SAFETY_STOCK = "SAFETY_STOCK"
    SETUP_MINIMIZATION = "SETUP_MINIMIZATION"
    SHIFT_LIMIT = "SHIFT_LIMIT"


class RuleEnforcement(StrEnum):
    """Whether a rule is a hard constraint or a soft (weighted) preference."""

    HARD = "HARD"
    SOFT = "SOFT"


# ---------------------------------------------------------------------------
# Risk detection
# ---------------------------------------------------------------------------
class RiskType(StrEnum):
    """Category of an operational risk detected after scheduling."""

    MACHINE_OVERLOAD = "MACHINE_OVERLOAD"
    CAPACITY_SHORTAGE = "CAPACITY_SHORTAGE"
    MATERIAL_SHORTAGE = "MATERIAL_SHORTAGE"
    INVENTORY_BELOW_SAFETY_STOCK = "INVENTORY_BELOW_SAFETY_STOCK"
    WORKER_CONFLICT = "WORKER_CONFLICT"
    DELAYED_ORDER = "DELAYED_ORDER"
    MAINTENANCE_CONFLICT = "MAINTENANCE_CONFLICT"


class RiskSeverity(StrEnum):
    """Severity classification of a detected risk."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
class RecommendationAction(StrEnum):
    """Concrete corrective action proposed by the recommendation engine."""

    ASSIGN_ALTERNATE_MACHINE = "ASSIGN_ALTERNATE_MACHINE"
    ASSIGN_ALTERNATE_WORKER = "ASSIGN_ALTERNATE_WORKER"
    SPLIT_BATCH = "SPLIT_BATCH"
    RESCHEDULE_MAINTENANCE = "RESCHEDULE_MAINTENANCE"
    APPROVE_OVERTIME = "APPROVE_OVERTIME"
    EXPEDITE_PURCHASE_ORDER = "EXPEDITE_PURCHASE_ORDER"
    ADD_SHIFT = "ADD_SHIFT"
    REPLENISH_ALTERNATE_SUPPLIER = "REPLENISH_ALTERNATE_SUPPLIER"


class RecommendationFeasibility(StrEnum):
    """Feasibility assessment of a proposed recommendation."""

    FEASIBLE = "FEASIBLE"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    INFEASIBLE = "INFEASIBLE"


# ---------------------------------------------------------------------------
# Scenario planning
# ---------------------------------------------------------------------------
class ScenarioType(StrEnum):
    """Predefined planning scenarios compared side by side."""

    CURRENT_PLAN = "CURRENT_PLAN"
    OVERTIME_ENABLED = "OVERTIME_ENABLED"
    ALTERNATE_MACHINES = "ALTERNATE_MACHINES"
    ADDITIONAL_SHIFT = "ADDITIONAL_SHIFT"


# ---------------------------------------------------------------------------
# Daily simulator / change log
# ---------------------------------------------------------------------------
class ChangeEventType(StrEnum):
    """Type of operational change applied when a new production day evolves."""

    NEW_PRODUCTION_ORDER = "NEW_PRODUCTION_ORDER"
    ORDER_CANCELLATION = "ORDER_CANCELLATION"
    PRIORITY_CHANGE = "PRIORITY_CHANGE"
    MACHINE_BREAKDOWN = "MACHINE_BREAKDOWN"
    PLANNED_MAINTENANCE = "PLANNED_MAINTENANCE"
    WORKER_LEAVE = "WORKER_LEAVE"
    SHIFT_CHANGE = "SHIFT_CHANGE"
    OVERTIME_APPROVAL = "OVERTIME_APPROVAL"
    INVENTORY_CONSUMPTION = "INVENTORY_CONSUMPTION"
    MATERIAL_REPLENISHMENT = "MATERIAL_REPLENISHMENT"
    SUPPLIER_DELAY = "SUPPLIER_DELAY"
    PURCHASE_ORDER_ARRIVAL = "PURCHASE_ORDER_ARRIVAL"
    CAPACITY_CHANGE = "CAPACITY_CHANGE"


class SolverStatus(StrEnum):
    """Outcome of a CP-SAT solve, mirrored from the optimization engine."""

    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    UNKNOWN = "UNKNOWN"
    MODEL_INVALID = "MODEL_INVALID"
