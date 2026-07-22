"""Detector: maintenance conflicts.

Detects any scheduled operation whose time window overlaps a maintenance window
on the same machine. The optimizer normally prevents this; the detector is a
consistency safeguard that surfaces conflicts introduced by data changes or a
disabled maintenance constraint.
"""

from __future__ import annotations

from app.domain.enums import RiskSeverity, RiskType
from app.risk.result import RiskBuilder, RiskContext


def detect(ctx: RiskContext, builder: RiskBuilder) -> None:
    """Emit a MAINTENANCE_CONFLICT risk per overlapping operation/window."""
    maintenance_by_machine: dict[str, list] = {}
    for window in ctx.state.machine_maintenance:
        maintenance_by_machine.setdefault(window.machine_id, []).append(window)

    for machine_id, ops in ctx.ops_by_machine.items():
        windows = maintenance_by_machine.get(machine_id)
        if not windows:
            continue
        for op in ops:
            for window in windows:
                overlaps = op.start < window.end and window.start < op.end
                if not overlaps:
                    continue
                builder.add(
                    risk_type=RiskType.MAINTENANCE_CONFLICT,
                    severity=RiskSeverity.HIGH,
                    title=(
                        f"Operation {op.operation_id} overlaps maintenance on "
                        f"{machine_id}"
                    ),
                    description=(
                        f"Operation {op.operation_id} (order {op.order_id}) on machine "
                        f"{machine_id} overlaps maintenance window "
                        f"{window.maintenance_id}."
                    ),
                    affected_entities={
                        "machine_ids": [machine_id],
                        "operation_ids": [op.operation_id],
                        "maintenance_ids": [window.maintenance_id],
                    },
                    evidence={
                        "operation_start": op.start.isoformat(),
                        "operation_end": op.end.isoformat(),
                        "maintenance_start": window.start.isoformat(),
                        "maintenance_end": window.end.isoformat(),
                    },
                )
