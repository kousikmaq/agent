"""Simulator configuration.

All tunable parameters for the stateful daily factory simulator live here:
factory sizing (used to build the Day-0 baseline) and per-day event intensities
(probabilities and volumes used to evolve one production day into the next).

Values are deliberately data-only so operators can tune realism without
touching simulator logic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SimulatorConfig(BaseModel):
    """Tunable parameters governing baseline generation and daily evolution."""

    # --- Determinism ---
    base_seed: int = Field(
        default=42, description="Base RNG seed; combined with the date per day."
    )

    # --- Factory sizing (Day-0 baseline) ---
    work_centers: list[str] = Field(
        default_factory=lambda: [
            "CUTTING",
            "MACHINING",
            "WELDING",
            "ASSEMBLY",
            "PAINTING",
            "QC",
        ],
        description="Ordered list of work centers (also the canonical route order).",
    )
    machines_per_work_center: int = Field(default=3, ge=1)
    num_finished_products: int = Field(default=12, ge=1)
    num_raw_materials: int = Field(default=16, ge=1)
    operations_per_routing_min: int = Field(default=3, ge=1)
    operations_per_routing_max: int = Field(default=6, ge=1)
    components_per_bom_min: int = Field(default=2, ge=0)
    components_per_bom_max: int = Field(default=4, ge=0)
    num_workers: int = Field(default=40, ge=1)
    num_customers: int = Field(default=8, ge=1)
    num_suppliers: int = Field(default=6, ge=1)
    initial_open_purchase_orders: int = Field(default=10, ge=0)
    initial_production_orders: int = Field(default=30, ge=0)
    planning_horizon_days: int = Field(default=30, ge=1)

    # --- Order parameters ---
    order_quantity_min: int = Field(default=20, ge=1)
    order_quantity_max: int = Field(default=500, ge=1)
    order_lead_days_min: int = Field(default=3, ge=0)
    order_lead_days_max: int = Field(default=21, ge=0)

    # --- Shifts machines operate on (workers may cover all shifts) ---
    machine_operating_shift_ids: list[str] = Field(
        default_factory=lambda: ["SHIFT_MORNING", "SHIFT_AFTERNOON"],
    )

    # --- Daily event intensities ---
    new_orders_mean: float = Field(
        default=4.0, ge=0, description="Mean number of new orders per day (Poisson-ish)."
    )
    order_cancel_probability: float = Field(default=0.03, ge=0, le=1)
    priority_change_probability: float = Field(default=0.05, ge=0, le=1)

    machine_breakdown_probability: float = Field(default=0.04, ge=0, le=1)
    machine_recovery_probability: float = Field(default=0.6, ge=0, le=1)
    planned_maintenance_probability: float = Field(default=0.05, ge=0, le=1)
    planned_maintenance_horizon_days: int = Field(default=5, ge=1)

    worker_leave_probability: float = Field(default=0.06, ge=0, le=1)
    shift_change_probability: float = Field(default=0.05, ge=0, le=1)
    overtime_approval_probability: float = Field(default=0.10, ge=0, le=1)
    overtime_minutes: int = Field(default=120, ge=0)

    inventory_consumption_fraction_min: float = Field(default=0.02, ge=0, le=1)
    inventory_consumption_fraction_max: float = Field(default=0.20, ge=0, le=1)

    supplier_delay_probability: float = Field(default=0.15, ge=0, le=1)
    supplier_delay_days_min: int = Field(default=1, ge=0)
    supplier_delay_days_max: int = Field(default=5, ge=0)
    replenish_when_below_reorder: bool = Field(default=True)

    capacity_change_probability: float = Field(default=0.05, ge=0, le=1)
    capacity_change_fraction: float = Field(
        default=0.15, ge=0, le=1, description="Max +/- fractional capacity shift."
    )

    def seed_for_date(self, date_ordinal: int) -> int:
        """Return a deterministic per-day RNG seed derived from the base seed."""
        return self.base_seed * 1_000_003 + date_ordinal
