"""State transforms that apply a recommended fix, then let the day re-solve.

Each transform mutates a (deep-copied) :class:`FactoryState` so the
deterministic pipeline can re-solve with the fix in place. Where a fix mirrors
an existing what-if scenario the scenario transform is reused; the remaining
actions (worker, maintenance, material) have lightweight transforms here.
"""

from __future__ import annotations

from app.core.exceptions import ValidationError
from app.domain.enums import RecommendationAction, WorkerAvailabilityStatus
from app.domain.models.factory_state import FactoryState
from app.domain.models.inventory import InventoryItem
from app.scenario.transforms import (
    apply_additional_shift,
    apply_alternate_machines,
    apply_overtime,
)

# Generous top-up so replenished components comfortably cover demand.
_REPLENISH_BUFFER = 1_000_000.0


def _reschedule_maintenance(
    state: FactoryState, machine_ids: list[str]
) -> FactoryState:
    """Clear maintenance windows blocking the affected machines (or all)."""
    ids = set(machine_ids)
    if ids:
        state.machine_maintenance = [
            m for m in state.machine_maintenance if m.machine_id not in ids
        ]
    else:
        state.machine_maintenance = []
    return state


def _free_up_workers(state: FactoryState, worker_ids: list[str]) -> FactoryState:
    """Restore staffing: mark workers available and enable overtime.

    ``worker_ids`` narrows the change when known (double-booking); otherwise
    (an unstaffed operation) all workers are freed up so the solver has the
    widest staffing choice.
    """
    ids = set(worker_ids)
    state.worker_availability = [
        wa
        for wa in state.worker_availability
        if wa.status == WorkerAvailabilityStatus.AVAILABLE
        or (ids and wa.worker_id not in ids)
    ]
    for worker in state.workers:
        if not ids or worker.worker_id in ids:
            worker.overtime_allowed = True
    return state


def _replenish(state: FactoryState, product_ids: list[str]) -> FactoryState:
    """Top up on-hand stock for the affected components to clear shortages."""
    ids = set(product_ids)
    by_product = {item.product_id: item for item in state.inventory}
    targets = ids or set(by_product)
    for pid in targets:
        item = by_product.get(pid)
        if item is None:
            state.inventory.append(
                InventoryItem(
                    product_id=pid,
                    on_hand=_REPLENISH_BUFFER,
                    allocated=0.0,
                    safety_stock=0.0,
                    reorder_point=0.0,
                )
            )
        else:
            item.on_hand = item.allocated + item.safety_stock + _REPLENISH_BUFFER
    return state


def apply_fix(
    state: FactoryState,
    action: RecommendationAction,
    targets: dict[str, list[str]],
) -> FactoryState:
    """Apply the transform for ``action`` to ``state`` and return it.

    ``targets`` carries the affected entity ids (machine_ids, worker_ids,
    product_ids) from the risk being mitigated.
    """
    machine_ids = targets.get("machine_ids", [])
    worker_ids = targets.get("worker_ids", [])
    product_ids = targets.get("product_ids", [])

    if action == RecommendationAction.ASSIGN_ALTERNATE_MACHINE:
        return apply_alternate_machines(state, {})
    if action == RecommendationAction.ADD_SHIFT:
        return apply_additional_shift(state, {})
    if action == RecommendationAction.APPROVE_OVERTIME:
        return apply_overtime(state, {})
    if action == RecommendationAction.RESCHEDULE_MAINTENANCE:
        return _reschedule_maintenance(state, machine_ids)
    if action == RecommendationAction.ASSIGN_ALTERNATE_WORKER:
        return _free_up_workers(state, worker_ids)
    if action in (
        RecommendationAction.EXPEDITE_PURCHASE_ORDER,
        RecommendationAction.REPLENISH_ALTERNATE_SUPPLIER,
    ):
        return _replenish(state, product_ids)
    if action == RecommendationAction.SPLIT_BATCH:
        # No batch-splitting transform yet; fall back to capacity relief.
        return apply_overtime(state, {})

    raise ValidationError(
        f"Unsupported fix action: {action}.",
        details={"action": str(action)},
    )
