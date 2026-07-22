"""Recommendation endpoint: retrieve recommendations for a business date."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_results_store
from app.core.exceptions import NotFoundError
from app.domain.models.recommendation import RecommendationSet
from app.services import ResultsStore

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get(
    "/{business_date}",
    response_model=RecommendationSet,
    summary="Get recommendations",
)
async def get_recommendations(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> RecommendationSet:
    """Return the persisted recommendations for a business date."""
    recommendations = store.load_recommendations(business_date)
    if recommendations is None:
        raise NotFoundError(
            f"No recommendations found for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    return recommendations
