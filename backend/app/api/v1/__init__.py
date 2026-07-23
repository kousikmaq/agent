"""API version 1.

Aggregates all v1 routers into a single :data:`api_router` that the
application mounts under the configured ``/api/v1`` prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes_analytics import router as analytics_router
from app.api.v1.routes_actions import router as actions_router
from app.api.v1.routes_chat import router as chat_router
from app.api.v1.routes_data import router as data_router
from app.api.v1.routes_deliveries import router as deliveries_router
from app.api.v1.routes_health import router as health_router
from app.api.v1.routes_materials import router as materials_router
from app.api.v1.routes_orchestrate import router as orchestrate_router
from app.api.v1.routes_recommendations import router as recommendations_router
from app.api.v1.routes_risks import router as risks_router
from app.api.v1.routes_scenarios import router as scenarios_router
from app.api.v1.routes_schedule import router as schedule_router
from app.api.v1.routes_shopfloor import router as shopfloor_router
from app.api.v1.routes_weekly import router as weekly_router

# Root router for the v1 API surface.
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(data_router)
api_router.include_router(schedule_router)
api_router.include_router(analytics_router)
api_router.include_router(deliveries_router)
api_router.include_router(weekly_router)
api_router.include_router(shopfloor_router)
api_router.include_router(materials_router)
api_router.include_router(risks_router)
api_router.include_router(recommendations_router)
api_router.include_router(scenarios_router)
api_router.include_router(chat_router)
api_router.include_router(orchestrate_router)
api_router.include_router(actions_router)

__all__ = ["api_router"]
