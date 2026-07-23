"""Materials availability endpoint.

Serves the full materials/inventory availability report (on-hand, allocated,
net available, and any shortage vs reorder/safety) for a business date, powering
the Materials tab and its place-order action.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.analytics.materials import MaterialsReport, build_materials_report
from app.api.v1.deps import get_data_source
from app.core.exceptions import DataIngestionError, NotFoundError
from app.ingestion import CsvDataSource

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
