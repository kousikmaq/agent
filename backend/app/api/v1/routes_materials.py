"""Materials availability endpoint.

Serves the full materials/inventory availability report (on-hand, allocated,
net available, and any shortage vs reorder/safety) for a business date, powering
the Materials tab and its place-order action.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.analytics.materials import MaterialsReport, build_materials_report
from app.api.v1.deps import get_data_source, get_orchestrator
from app.api.v1.schemas import MaterialReorderRequest
from app.core.exceptions import DataIngestionError, NotFoundError
from app.ingestion import CsvDataSource
from app.services import PlanningOrchestrator

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get(
    "/{business_date}",
    response_model=MaterialsReport,
    summary="Get materials availability and shortages",
)
async def get_materials(
    business_date: str,
    source: Annotated[CsvDataSource, Depends(get_data_source)],
) -> MaterialsReport:
    """Return the materials availability report for a business date."""
    try:
        state = source.load(business_date)
    except DataIngestionError as exc:
        raise NotFoundError(
            f"No factory snapshot found for {business_date}.",
            details={"business_date": business_date},
        ) from exc
    return build_materials_report(state)


@router.get(
    "/{business_date}/purchase-orders",
    summary="List purchase orders placed for a business date",
)
async def get_purchase_orders(
    business_date: str,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> list[dict]:
    """Return the day's placed purchase orders (auto or manual), newest last."""
    return orchestrator.store.load_purchase_orders(business_date)


@router.post(
    "/{business_date}/reorder",
    summary="Place a purchase order for a material (manual)",
)
async def reorder_material(
    business_date: str,
    request: MaterialReorderRequest,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> dict:
    """Place (email + log) a purchase order for one material and return it."""
    return orchestrator.reorder_material(
        business_date,
        request.product_id,
        quantity=request.quantity,
        reason=request.reason or "Manual replenishment request.",
        mode="manual",
    )


@router.post(
    "/{business_date}/auto-reorder",
    summary="Autonomously place POs for materials below safety + reorder",
)
async def auto_reorder(
    business_date: str,
    orchestrator: Annotated[PlanningOrchestrator, Depends(get_orchestrator)],
) -> dict:
    """Auto-place POs for critically-low materials (once per material per day)."""
    return orchestrator.auto_reorder(business_date)

