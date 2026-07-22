"""FactoryState - the canonical aggregate consumed by the deterministic core.

``FactoryState`` is the single in-memory representation of one production day's
operational data. The ingestion layer builds it from any data source (CSV
today, ERP/MES tomorrow), and every downstream engine (rules, optimization,
analytics, risk, recommendation, scenario) reads exclusively from it. This is
what makes the data source swappable without touching business logic.
"""

from __future__ import annotations

from pydantic import Field

from app.domain.models.base import DomainModel
from app.domain.models.bom import BomLine
from app.domain.models.business_rule import BusinessRule
from app.domain.models.customer import Customer
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
from app.domain.models.routing import Routing
from app.domain.models.shift_calendar import Shift, ShiftCalendar
from app.domain.models.supplier import Supplier
from app.domain.models.workforce import Worker, WorkerAvailability, WorkerSkill


class FactoryState(DomainModel):
    """A complete, validated snapshot of the factory for a single day.

    Collections are stored as lists to mirror the source data faithfully;
    later phases build lookup indexes as needed. No business logic lives here.
    """

    business_date: str = Field(..., description="Day this state represents (YYYY-MM-DD).")

    # --- Demand ---
    production_orders: list[ProductionOrder] = Field(default_factory=list)
    customers: list[Customer] = Field(default_factory=list)

    # --- Product / process definition ---
    products: list[Product] = Field(default_factory=list)
    routings: list[Routing] = Field(default_factory=list)
    boms: list[BomLine] = Field(default_factory=list)

    # --- Resources: machines ---
    machines: list[Machine] = Field(default_factory=list)
    machine_availability: list[MachineAvailability] = Field(default_factory=list)
    machine_maintenance: list[MachineMaintenance] = Field(default_factory=list)

    # --- Resources: workforce ---
    workers: list[Worker] = Field(default_factory=list)
    worker_skills: list[WorkerSkill] = Field(default_factory=list)
    worker_availability: list[WorkerAvailability] = Field(default_factory=list)

    # --- Calendars ---
    shifts: list[Shift] = Field(default_factory=list)
    shift_calendars: list[ShiftCalendar] = Field(default_factory=list)
    plant_calendar: list[PlantCalendar] = Field(default_factory=list)

    # --- Materials & procurement ---
    inventory: list[InventoryItem] = Field(default_factory=list)
    suppliers: list[Supplier] = Field(default_factory=list)
    purchase_orders: list[PurchaseOrder] = Field(default_factory=list)

    # --- Policy ---
    business_rules: list[BusinessRule] = Field(default_factory=list)
