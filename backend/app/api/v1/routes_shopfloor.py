"""Shop floor status endpoint.

Serves the live shop-floor status board (machines, workers, orders, materials,
risk headline) computed from the day's factory snapshot and today's risk report.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.analytics import ShopFloorStatus, build_shopfloor_status
from app.api.v1.deps import get_data_source, get_results_store
from app.core.exceptions import DataIngestionError, NotFoundError
from app.ingestion import CsvDataSource
from app.services import ResultsStore

router = APIRouter(prefix="/shopfloor", tags=["shopfloor"])


@router.get(
    "/{business_date}",
    response_model=ShopFloorStatus,
    summary="Get live shop-floor status",
)
async def get_shopfloor(
    business_date: str,
    source: Annotated[CsvDataSource, Depends(get_data_source)],
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> ShopFloorStatus:
    """Return the current shop-floor status for a business date.

    Uses the day's snapshot (always available for a generated day) plus today's
    persisted risk report when the day has been planned.
    """
    try:
        state = source.load(business_date)
    except DataIngestionError as exc:
        raise NotFoundError(
            f"No factory snapshot found for {business_date}.",
            details={"business_date": business_date},
        ) from exc
    risks = store.load_risks(business_date)
    return build_shopfloor_status(state, risks)
