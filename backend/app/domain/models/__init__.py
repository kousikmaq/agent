"""Canonical domain models.

Re-exports every domain entity and DTO for convenient, stable imports, e.g.::

    from app.domain.models import ProductionOrder, FactoryState

Grouped by category: master data, resources, calendars, materials, policy,
computed results, and aggregates.
"""

from __future__ import annotations

from app.domain.models.analytics import KpiSet
from app.domain.models.base import DomainModel, FrozenDomainModel
from app.domain.models.bom import BomLine
from app.domain.models.business_rule import BusinessRule
from app.domain.models.change_log import ChangeEvent, ChangeLog
from app.domain.models.customer import Customer
from app.domain.models.explanation import ExplanationContext
from app.domain.models.factory_state import FactoryState
from app.domain.models.inventory import InventoryItem
from app.domain.models.machine import (
    Machine,
    MachineAvailability,
    MachineMaintenance,
)
from app.domain.models.plant_calendar import PlantCalendar
from app.domain.models.product import Product
from app.domain.models.production_order import ProductionOrder
from app.domain.models.purchase_order import PurchaseOrder
from app.domain.models.recommendation import Recommendation, RecommendationSet
from app.domain.models.risk import Risk, RiskReport
from app.domain.models.routing import Operation, Routing
from app.domain.models.scenario import (
    ScenarioComparison,
    ScenarioDefinition,
    ScenarioResult,
)
from app.domain.models.schedule import ScheduledOperation, ScheduleResult
from app.domain.models.shift_calendar import Shift, ShiftCalendar
from app.domain.models.supplier import Supplier
from app.domain.models.workforce import Worker, WorkerAvailability, WorkerSkill

__all__ = [
    # Base
    "DomainModel",
    "FrozenDomainModel",
    # Master data
    "Customer",
    "Product",
    "Routing",
    "Operation",
    "ProductionOrder",
    # Resources
    "Machine",
    "MachineAvailability",
    "MachineMaintenance",
    "Worker",
    "WorkerSkill",
    "WorkerAvailability",
    # Calendars
    "Shift",
    "ShiftCalendar",
    "PlantCalendar",
    # Materials & procurement
    "InventoryItem",
    "BomLine",
    "Supplier",
    "PurchaseOrder",
    # Policy
    "BusinessRule",
    # Computed results
    "ScheduledOperation",
    "ScheduleResult",
    "KpiSet",
    "Risk",
    "RiskReport",
    "Recommendation",
    "RecommendationSet",
    "ScenarioDefinition",
    "ScenarioResult",
    "ScenarioComparison",
    "ChangeEvent",
    "ChangeLog",
    # Aggregates
    "FactoryState",
    "ExplanationContext",
]
