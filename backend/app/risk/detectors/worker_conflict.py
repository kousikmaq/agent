"""Detector: worker conflicts.

Detects two kinds of workforce risk:

* **Unstaffed skill** - a scheduled operation that requires a skill was placed
  without a worker (no available qualified worker existed).
* **Double booking** - the same worker is assigned two operations whose time
  windows overlap (a data/consistency safeguard; the optimizer normally
  prevents this).
"""

from __future__ import annotations

from app.domain.enums import RiskSeverity, RiskType
from app.risk.result import RiskBuilder, RiskContext


def _detect_unstaffed(ctx: RiskContext, builder: RiskBuilder) -> None:
    for op in ctx.schedule.scheduled_operations:
        operation = ctx.operation_by_id.get(op.operation_id)
        if operation is None or not operation.required_skill:
            continue
        if op.worker_id:
            continue
        builder.add(
            risk_type=RiskType.WORKER_CONFLICT,
            severity=RiskSeverity.HIGH,
            title=f"Operation {op.operation_id} is unstaffed",
            description=(
                f"Operation {op.operation_id} (order {op.order_id}) requires skill "
                f"{operation.required_skill} but no worker was assigned."
            ),
            affected_entities={
                "order_ids": [op.order_id],
                "operation_ids": [op.operation_id],
            },
            evidence={"required_skill": operation.required_skill},
        )


def _detect_double_booking(ctx: RiskContext, builder: RiskBuilder) -> None:
    for worker_id, ops in ctx.ops_by_worker.items():
        ordered = sorted(ops, key=lambda o: o.start)
        for previous, current in zip(ordered, ordered[1:]):
            if current.start < previous.end:
                builder.add(
                    risk_type=RiskType.WORKER_CONFLICT,
                    severity=RiskSeverity.CRITICAL,
                    title=f"Worker {worker_id} is double-booked",
                    description=(
                        f"Worker {worker_id} is assigned overlapping operations "
                        f"{previous.operation_id} and {current.operation_id}."
                    ),
                    affected_entities={
                        "worker_ids": [worker_id],
                        "operation_ids": [previous.operation_id, current.operation_id],
                    },
                    evidence={
                        "first_end": previous.end.isoformat(),
                        "second_start": current.start.isoformat(),
                    },
                )


def detect(ctx: RiskContext, builder: RiskBuilder) -> None:
    """Emit WORKER_CONFLICT risks for unstaffed operations and double bookings."""
    _detect_unstaffed(ctx, builder)
    _detect_double_booking(ctx, builder)
