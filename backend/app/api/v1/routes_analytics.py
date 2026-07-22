"""Analytics endpoint: retrieve computed KPIs for a business date."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_results_store
from app.core.exceptions import NotFoundError
from app.domain.models.analytics import KpiSet
from app.services import ResultsStore

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/{business_date}", response_model=KpiSet, summary="Get KPIs")
async def get_kpis(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> KpiSet:
    """Return the persisted KPIs for a business date."""
    kpis = store.load_kpis(business_date)
    if kpis is None:
        raise NotFoundError(
            f"No KPIs found for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    return kpis
