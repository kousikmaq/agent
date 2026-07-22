"""Weekly plan endpoint.

Serves the 7-day plan (per-day targets) and daily progress-to-date, computed
from the persisted schedule and the day's factory snapshot.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.analytics import WeeklyPlanReport, build_weekly_plan
from app.api.v1.deps import get_data_source, get_results_store
from app.core.exceptions import NotFoundError
from app.ingestion import CsvDataSource
from app.services import ResultsStore
from app.utils.datetime_utils import parse_business_date

router = APIRouter(prefix="/weekly", tags=["weekly"])


@router.get(
    "/{business_date}",
    response_model=WeeklyPlanReport,
    summary="Get the weekly plan and daily progress",
)
async def get_weekly_plan(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
    source: Annotated[CsvDataSource, Depends(get_data_source)],
    as_of: Annotated[str | None, Query()] = None,
) -> WeeklyPlanReport:
    """Return the Monday-Saturday plan for ``business_date``'s week.

    The plan is anchored on the week's Monday (so early-week work is included)
    and progress is measured as of ``as_of`` (defaults to ``business_date``).
    """
    anchor = parse_business_date(business_date)
    monday = (anchor - timedelta(days=anchor.weekday())).isoformat()
    # Prefer the Monday's schedule (spans the whole week); fall back to the
    # selected day if the week has not been planned from Monday.
    schedule = store.load_schedule(monday) or store.load_schedule(business_date)
    if schedule is None:
        raise NotFoundError(
            f"No schedule found for the week of {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    state = source.load(schedule.business_date)
    return build_weekly_plan(state, schedule, as_of=as_of or business_date)

