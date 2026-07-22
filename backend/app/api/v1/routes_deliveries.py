"""Delivery commitments endpoint.

Serves the red/amber/green delivery board for orders due within a horizon,
computed from the persisted schedule and the day's factory snapshot.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.analytics import (
    DeliveryDriftReport,
    DeliveryReport,
    build_delivery_drift,
    build_delivery_report,
)
from app.api.v1.deps import get_data_source, get_results_store
from app.core.exceptions import NotFoundError
from app.ingestion import CsvDataSource
from app.services import ResultsStore

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get(
    "/{business_date}",
    response_model=DeliveryReport,
    summary="Get delivery commitments",
)
async def get_deliveries(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
    source: Annotated[CsvDataSource, Depends(get_data_source)],
    horizon_days: Annotated[int, Query(ge=1, le=60)] = 7,
) -> DeliveryReport:
    """Return delivery status per order due within ``horizon_days``."""
    schedule = store.load_schedule(business_date)
    if schedule is None:
        raise NotFoundError(
            f"No schedule found for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    state = source.load(business_date)
    return build_delivery_report(state, schedule, horizon_days=horizon_days)


@router.get(
    "/{business_date}/drift",
    response_model=DeliveryDriftReport,
    summary="Get delivery commitment drift vs the previous plan",
)
async def get_delivery_drift(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
    source: Annotated[CsvDataSource, Depends(get_data_source)],
    horizon_days: Annotated[int, Query(ge=1, le=60)] = 7,
) -> DeliveryDriftReport:
    """Return day-over-day movement of commitments vs the previous planned day."""
    schedule = store.load_schedule(business_date)
    if schedule is None:
        raise NotFoundError(
            f"No schedule found for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    current = build_delivery_report(
        source.load(business_date), schedule, horizon_days=horizon_days
    )

    # Find the latest prior date that has both a schedule and a snapshot.
    previous = None
    prior_dates = [d for d in source.available_dates() if d < business_date]
    for prev_date in sorted(prior_dates, reverse=True):
        prev_schedule = store.load_schedule(prev_date)
        if prev_schedule is None:
            continue
        try:
            prev_state = source.load(prev_date)
        except Exception:  # noqa: BLE001 - missing snapshot, skip
            continue
        previous = build_delivery_report(
            prev_state, prev_schedule, horizon_days=horizon_days
        )
        break

    return build_delivery_drift(current, previous)
