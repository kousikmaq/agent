"""Health check endpoints.

Provides lightweight liveness and readiness probes used by orchestration
platforms (Docker, Kubernetes) and monitoring. These endpoints contain no
business logic and never touch the optimization engine.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.schemas import HealthResponse
from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Return basic service liveness information.

    A ``200`` response indicates the process is running and able to serve
    requests. Used as a container/orchestrator liveness probe.
    """
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/ready", response_model=HealthResponse, summary="Readiness probe")
async def ready(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Return service readiness information.

    In later phases this probe will additionally verify downstream
    dependencies (dataset availability, Azure OpenAI connectivity). For the
    foundation phase it mirrors the liveness response.
    """
    return HealthResponse(
        status="ready",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
