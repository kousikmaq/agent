"""Data endpoints: available snapshots, snapshot retrieval, and generation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_data_source, get_simulator_engine
from app.api.v1.schemas import (
    DatesResponse,
    GenerateDataRequest,
    GenerateDataResponse,
)
from app.core.exceptions import ValidationError
from app.domain.models.factory_state import FactoryState
from app.ingestion import CsvDataSource
from app.utils.datetime_utils import parse_business_date
from simulator.engine import SimulatorEngine

router = APIRouter(prefix="/data", tags=["data"])


def _validate_date(business_date: str) -> None:
    try:
        parse_business_date(business_date)
    except ValueError as exc:
        raise ValidationError(
            f"Invalid business date '{business_date}'; expected YYYY-MM-DD."
        ) from exc


@router.get("/dates", response_model=DatesResponse, summary="List snapshot dates")
async def list_dates(
    source: Annotated[CsvDataSource, Depends(get_data_source)],
) -> DatesResponse:
    """Return the business dates available in the datasets directory."""
    return DatesResponse(dates=source.available_dates())


@router.get("/{business_date}", response_model=FactoryState, summary="Get a snapshot")
async def get_snapshot(
    business_date: str,
    source: Annotated[CsvDataSource, Depends(get_data_source)],
) -> FactoryState:
    """Return the validated factory snapshot for a business date."""
    _validate_date(business_date)
    return source.load(business_date)


@router.post(
    "/generate",
    response_model=GenerateDataResponse,
    summary="Generate a daily snapshot",
)
async def generate_snapshot(
    request: GenerateDataRequest,
    engine: Annotated[SimulatorEngine, Depends(get_simulator_engine)],
) -> GenerateDataResponse:
    """Generate a stateful daily snapshot via the factory simulator."""
    day = parse_business_date(request.business_date)
    _, change_log = engine.generate_day(day)
    return GenerateDataResponse(
        business_date=request.business_date, change_events=len(change_log.events)
    )
