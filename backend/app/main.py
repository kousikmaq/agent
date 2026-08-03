"""Application factory and FastAPI entrypoint.

Assembles the FastAPI application: configuration, logging, CORS, exception
handlers, versioned routers, and lifespan (startup/shutdown) hooks. Keeping
construction inside :func:`create_app` makes the app trivially testable and
avoids import-time side effects.
"""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router as api_v1_router
from app.config import Settings, get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.utils.file_utils import ensure_dir

logger = get_logger(__name__)


def _build_lifespan(settings: Settings):
    """Create a lifespan context manager bound to the given settings."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # --- Startup ---
        logger.info(
            "Starting %s v%s (%s)",
            settings.app_name,
            settings.app_version,
            settings.environment,
        )
        # Ensure the data/output directories exist so later phases can rely on
        # them. This is infrastructure setup, not business logic.
        ensure_dir(settings.datasets_dir)
        ensure_dir(settings.outputs_dir)
        logger.info("Datasets dir: %s", settings.datasets_dir)
        logger.info("Outputs dir:  %s", settings.outputs_dir)

        # Start the daily/weekly planning cadence (refresh today's plan; publish
        # next week's plans every Saturday). Runs in a daemon thread so solving
        # never blocks startup or the API, and is idempotent so it never
        # recomputes an already-planned day.
        stop_event: threading.Event | None = None
        if settings.enable_scheduler and not os.environ.get("PYTEST_CURRENT_TEST"):
            from app.services.orchestrator import PlanningOrchestrator
            from app.services.planning_scheduler import (
                PlanningScheduler,
                start_scheduler_thread,
            )
            from simulator.config import SimulatorConfig
            from simulator.engine import SimulatorEngine

            orchestrator = PlanningOrchestrator(
                datasets_dir=settings.datasets_dir, outputs_dir=settings.outputs_dir
            )
            simulator = SimulatorEngine(
                config=SimulatorConfig(scale_factor=settings.simulator_scale_factor),
                datasets_dir=settings.datasets_dir,
            )
            scheduler = PlanningScheduler(
                orchestrator, simulator, settings.datasets_dir
            )
            stop_event = threading.Event()
            start_scheduler_thread(scheduler, stop_event)
            logger.info("Daily/weekly planning scheduler started.")

        yield

        # --- Shutdown ---
        if stop_event is not None:
            stop_event.set()
        logger.info("Shutting down %s", settings.app_name)

    return lifespan


def create_app() -> FastAPI:
    """Build and return a fully configured FastAPI application instance."""
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=_build_lifespan(settings),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # --- Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Error handling ---
    register_exception_handlers(app)

    # --- Routers (versioned) ---
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.get("/", tags=["root"], summary="Service root")
    async def root() -> dict[str, str]:
        """Return a minimal service descriptor with links to API docs."""
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
        }

    return app


# Module-level application instance used by the ASGI server
# (e.g. ``uvicorn app.main:app``).
app = create_app()
