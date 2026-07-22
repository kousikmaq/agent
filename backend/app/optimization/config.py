"""Solver configuration options for the CP-SAT optimization engine.

Isolated, type-safe knobs controlling determinism, time budget, and objective
shaping. Defaults are sourced from the application settings so behaviour is
consistent across API, CLI, and tests.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import get_settings


class SolverOptions(BaseModel):
    """Tunable parameters for a single optimization run."""

    # --- Determinism & budget ---
    max_time_seconds: float = Field(
        default=30.0, gt=0, description="Wall-clock time budget for the solve."
    )
    random_seed: int = Field(default=42, description="Fixed seed for reproducibility.")
    num_search_workers: int = Field(
        default=8, ge=1, description="Parallel search workers (fixed for reproducibility)."
    )

    # --- Feature toggles (each maps to a modular constraint family) ---
    enable_workforce: bool = Field(
        default=True, description="Assign qualified workers and enforce worker no-overlap."
    )
    enable_materials: bool = Field(
        default=True, description="Delay orders until required materials are available."
    )
    enable_maintenance: bool = Field(
        default=True, description="Block machine time during maintenance windows."
    )
    enforce_hard_due_dates: bool = Field(
        default=False,
        description="If the policy marks due dates HARD, enforce them as constraints.",
    )

    # --- Batch processing (parallel-batch machines: paint booth, QC chamber) ---
    enable_batching: bool = Field(
        default=True,
        description=(
            "Enable parallel-batch machines: at batch work centers, several "
            "compatible operations run simultaneously in one batch cycle."
        ),
    )
    batch_work_centers: tuple[str, ...] = Field(
        default=("PAINTING", "QC"),
        description="Work centers whose machines process operations in batches.",
    )
    batch_capacity: int = Field(
        default=3,
        ge=1,
        description="Max operations processed simultaneously in one batch.",
    )
    batch_same_family_only: bool = Field(
        default=False,
        description=(
            "Only same product-family operations may share a batch. Off by "
            "default: enabling adds many constraints that hurt the time-limited "
            "solve; capacity-only batching yields better plans."
        ),
    )

    # --- Objective weights (secondary terms; tardiness is primary) ---
    late_order_weight: int = Field(
        default=1440,
        ge=0,
        description=(
            "Fixed penalty per late order, added on top of per-minute tardiness. "
            "Directly maximises the count of on-time orders (the delivery goal). "
            "Set to 0 to minimise only total lateness minutes."
        ),
    )
    makespan_weight: int = Field(
        default=1, ge=0, description="Weight on the schedule makespan (compactness)."
    )

    @classmethod
    def from_settings(cls) -> "SolverOptions":
        """Build options seeded from the global application settings."""
        settings = get_settings()
        return cls(
            max_time_seconds=settings.solver_max_time_seconds,
            random_seed=settings.solver_random_seed,
        )
