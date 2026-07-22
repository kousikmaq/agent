"""Shop floor status view.

A read-model over the current factory snapshot (and today's risk report) that
answers "what is happening on the floor right now, and are we on track?". It
summarises machine, worker, order, and material state - no scheduling logic and
no new business rules.
"""

from __future__ import annotations

from collections import Counter

from pydantic import Field

from app.domain.enums import MachineStatus, OrderStatus, WorkerAvailabilityStatus
from app.domain.models.base import FrozenDomainModel
from app.domain.models.factory_state import FactoryState
from app.domain.models.risk import RiskReport
from app.utils.datetime_utils import parse_business_date


class MachineStatusLine(FrozenDomainModel):
    """Current status of a single machine."""

    machine_id: str
    name: str
    work_center: str
    status: str


class MaterialShortLine(FrozenDomainModel):
    """An inventory item at or below its reorder/safety threshold."""

    product_id: str
    net_available: float
    safety_stock: float
    reorder_point: float
    below_safety: bool


class ShopFloorStatus(FrozenDomainModel):
    """Live shop-floor status summary for a business date."""

    business_date: str

    # Machines
    machine_total: int
    machine_available: int
    machine_running: int
    machine_idle: int
    machine_down: int
    machine_maintenance: int
    machines_attention: list[MachineStatusLine] = Field(default_factory=list)

    # Workers
    worker_total: int
    worker_available: int
    worker_unavailable: int

    # Orders
    orders_planned: int
    orders_released: int
    orders_in_progress: int
    orders_completed: int
    orders_cancelled: int

    # Materials
    materials_below_reorder: int
    materials_below_safety: int
    materials_attention: list[MaterialShortLine] = Field(default_factory=list)

    # Risk headline (from today's risk report, if available)
    open_risks: int
    critical_risks: int


def build_shopfloor_status(
    state: FactoryState, risks: RiskReport | None = None
) -> ShopFloorStatus:
    """Summarise the current shop-floor state from the snapshot (+ risks)."""
    business_date = parse_business_date(state.business_date)

    # --- Machines ---
    status_counts = Counter(m.status for m in state.machines)
    attention = [
        MachineStatusLine(
            machine_id=m.machine_id,
            name=m.name,
            work_center=m.work_center,
            status=str(m.status),
        )
        for m in state.machines
        if m.status in (MachineStatus.DOWN, MachineStatus.MAINTENANCE)
    ]

    # --- Workers (availability on the business date) ---
    worker_ids = {w.worker_id for w in state.workers}
    unavailable = {
        r.worker_id
        for r in state.worker_availability
        if r.day == business_date
        and r.status != WorkerAvailabilityStatus.AVAILABLE
    }
    worker_total = len(worker_ids)
    worker_unavailable = len(unavailable & worker_ids)

    # --- Orders ---
    order_counts = Counter(o.status for o in state.production_orders)

    # --- Materials ---
    material_lines: list[MaterialShortLine] = []
    below_reorder = 0
    below_safety = 0
    for item in state.inventory:
        net = item.on_hand - item.allocated
        is_below_reorder = item.reorder_point > 0 and net < item.reorder_point
        is_below_safety = item.safety_stock > 0 and net < item.safety_stock
        if is_below_reorder or is_below_safety:
            below_reorder += 1 if is_below_reorder else 0
            below_safety += 1 if is_below_safety else 0
            material_lines.append(
                MaterialShortLine(
                    product_id=item.product_id,
                    net_available=round(net, 2),
                    safety_stock=item.safety_stock,
                    reorder_point=item.reorder_point,
                    below_safety=is_below_safety,
                )
            )
    material_lines.sort(key=lambda ln: (not ln.below_safety, ln.net_available))

    # --- Risk headline ---
    open_risks = len(risks.risks) if risks else 0
    critical_risks = (
        sum(1 for r in risks.risks if str(r.severity) == "CRITICAL") if risks else 0
    )

    return ShopFloorStatus(
        business_date=state.business_date,
        machine_total=len(state.machines),
        machine_available=status_counts.get(MachineStatus.AVAILABLE, 0),
        machine_running=status_counts.get(MachineStatus.RUNNING, 0),
        machine_idle=status_counts.get(MachineStatus.IDLE, 0),
        machine_down=status_counts.get(MachineStatus.DOWN, 0),
        machine_maintenance=status_counts.get(MachineStatus.MAINTENANCE, 0),
        machines_attention=attention,
        worker_total=worker_total,
        worker_available=worker_total - worker_unavailable,
        worker_unavailable=worker_unavailable,
        orders_planned=order_counts.get(OrderStatus.PLANNED, 0),
        orders_released=order_counts.get(OrderStatus.RELEASED, 0),
        orders_in_progress=order_counts.get(OrderStatus.IN_PROGRESS, 0),
        orders_completed=order_counts.get(OrderStatus.COMPLETED, 0),
        orders_cancelled=order_counts.get(OrderStatus.CANCELLED, 0),
        materials_below_reorder=below_reorder,
        materials_below_safety=below_safety,
        materials_attention=material_lines,
        open_risks=open_risks,
        critical_risks=critical_risks,
    )
