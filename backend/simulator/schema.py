"""CSV schema registry mapping FactoryState collections to files.

Shared by :mod:`simulator.writer` and :mod:`simulator.state_loader` so writing
and reading a daily snapshot are perfectly symmetric. Routings are handled
separately (split into ``routings.csv`` + ``operations.csv``) because they nest
their operations.
"""

from __future__ import annotations

from pydantic import BaseModel

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
from app.domain.models.shift_calendar import Shift, ShiftCalendar
from app.domain.models.supplier import Supplier
from app.domain.models.workforce import Worker, WorkerAvailability, WorkerSkill

# (filename, FactoryState attribute, model class) for flat, single-model files.
CSV_REGISTRY: tuple[tuple[str, str, type[BaseModel]], ...] = (
    ("customers.csv", "customers", Customer),
    ("products.csv", "products", Product),
    ("boms.csv", "boms", BomLine),
    ("machines.csv", "machines", Machine),
    ("machine_availability.csv", "machine_availability", MachineAvailability),
    ("machine_maintenance.csv", "machine_maintenance", MachineMaintenance),
    ("workers.csv", "workers", Worker),
    ("worker_skills.csv", "worker_skills", WorkerSkill),
    ("worker_availability.csv", "worker_availability", WorkerAvailability),
    ("shifts.csv", "shifts", Shift),
    ("shift_calendars.csv", "shift_calendars", ShiftCalendar),
    ("plant_calendar.csv", "plant_calendar", PlantCalendar),
    ("inventory.csv", "inventory", InventoryItem),
    ("suppliers.csv", "suppliers", Supplier),
    ("purchase_orders.csv", "purchase_orders", PurchaseOrder),
    ("production_orders.csv", "production_orders", ProductionOrder),
    ("business_rules.csv", "business_rules", BusinessRule),
)

ROUTINGS_FILE = "routings.csv"
OPERATIONS_FILE = "operations.csv"
CHANGE_LOG_FILE = "_change_log.csv"
