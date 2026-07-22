"""Global exception handlers and a standard error-response envelope.

Registers handlers on the FastAPI application so that every error - whether an
application-specific :class:`~app.core.exceptions.AppError`, a FastAPI request
validation error, or an unexpected exception - is returned to clients in a
single, predictable JSON shape.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)


def _error_body(
    *, code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build the standard error envelope returned by every handler."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all global exception handlers to ``app``."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("Application error [%s]: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                code=exc.code, message=exc.message, details=exc.details
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body(
                code="request_validation_error",
                message="Request validation failed.",
                details={"errors": exc.errors()},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                code="http_error",
                message=str(exc.detail),
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # Log the full exception for diagnostics but never leak internals.
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_error_body(
                code="internal_server_error",
                message="An unexpected error occurred.",
            ),
        )
