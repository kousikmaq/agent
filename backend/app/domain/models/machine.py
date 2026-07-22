"""Machine master data, daily availability, and maintenance windows."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, model_validator

from app.domain.enums import MachineStatus, MaintenanceType
from app.domain.models.base import DomainModel


class Machine(DomainModel):
    """A production resource on which operations are performed."""

    machine_id: str = Field(..., description="Unique machine identifier.")
    name: str = Field(..., description="Machine display name.")
    work_center: str = Field(
        ..., description="Work center / department the machine belongs to."
    )
    status: MachineStatus = Field(
        default=MachineStatus.AVAILABLE, description="Current machine status."
    )
    capacity_minutes_per_day: int = Field(
        default=1440,
        ge=0,
        description="Nominal available runtime per day, in minutes.",
    )
    efficiency_factor: float = Field(
        default=1.0,
        gt=0,
        le=1.0,
        description="Throughput multiplier (1.0 = nominal, <1.0 = degraded).",
    )


class MachineAvailability(DomainModel):
    """A dated availability window for a machine.

    Multiple windows may exist per machine per day (e.g. split shifts).
    """

    machine_id: str = Field(..., description="Machine the window applies to.")
    day: date = Field(..., description="Calendar day of the window.")
    available_from: datetime = Field(..., description="Window start (inclusive).")
    available_to: datetime = Field(..., description="Window end (exclusive).")

    @model_validator(mode="after")
    def _validate_window(self) -> "MachineAvailability":
        """Window end must be strictly after its start."""
        if self.available_to <= self.available_from:
            raise ValueError(
                f"Machine {self.machine_id}: available_to must be after available_from."
            )
        return self


class MachineMaintenance(DomainModel):
    """A planned or unplanned maintenance window blocking a machine."""

    maintenance_id: str = Field(..., description="Unique maintenance identifier.")
    machine_id: str = Field(..., description="Machine being maintained.")
    maintenance_type: MaintenanceType = Field(
        ..., description="Nature of the maintenance window."
    )
    start: datetime = Field(..., description="Maintenance start (inclusive).")
    end: datetime = Field(..., description="Maintenance end (exclusive).")
    description: str | None = Field(
        default=None, description="Optional free-text notes."
    )

    @model_validator(mode="after")
    def _validate_window(self) -> "MachineMaintenance":
        """Maintenance end must be strictly after its start."""
        if self.end <= self.start:
            raise ValueError(
                f"Maintenance {self.maintenance_id}: end must be after start."
            )
        return self
