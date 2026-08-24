"""FastAPI application factory and centralized exception mapping."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from smart_retail.api.dependencies import APIRuntime
from smart_retail.api.errors import ResourceNotFoundError
from smart_retail.api.models import ErrorResponse
from smart_retail.api.routes import cart, events, health, metrics, sessions
from smart_retail.application_state import ApplicationNotReadyError
from smart_retail.infrastructure.logging_config import log_event
from smart_retail.infrastructure.sqlite_repository import PersistenceError

LOGGER = logging.getLogger(__name__)


Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_api_app(
    runtime: APIRuntime,
    *,
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """Create an API over one already-composed realtime application instance."""
    application = FastAPI(
        title="Smart Retail Checkout API",
        summary="Business state for the local vision-assisted checkout demo",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        responses={
            status.HTTP_422_UNPROCESSABLE_CONTENT: {
                "model": ErrorResponse,
                "description": "Request validation failed",
            },
            status.HTTP_500_INTERNAL_SERVER_ERROR: {
                "model": ErrorResponse,
                "description": "Unexpected server error",
            },
        },
        lifespan=lifespan,
    )
    application.state.runtime = runtime

    application.include_router(health.router)
    application.include_router(cart.router, prefix="/api/v1")
    application.include_router(events.router, prefix="/api/v1")
    application.include_router(sessions.router, prefix="/api/v1")
    application.include_router(metrics.router, prefix="/api/v1")

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(ResourceNotFoundError)
    async def handle_not_found(
        request: Request,
        error: ResourceNotFoundError,
    ) -> JSONResponse:
        return _error_response(status.HTTP_404_NOT_FOUND, error.code, error.message)

    @application.exception_handler(PersistenceError)
    async def handle_persistence_failure(
        request: Request,
        error: PersistenceError,
    ) -> JSONResponse:
        log_event(
            LOGGER,
            logging.ERROR,
            "api_persistence_failed",
            "API persistence operation failed",
            exc_info=True,
            method=request.method,
            path=request.url.path,
            error_type=type(error).__name__,
        )
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "persistence_unavailable",
            "Checkout history is temporarily unavailable.",
        )

    @application.exception_handler(ApplicationNotReadyError)
    async def handle_application_not_ready(
        request: Request,
        error: ApplicationNotReadyError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "application_not_ready",
            "The realtime checkout application is not running.",
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_failure(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "Request validation failed.",
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_failure(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        log_event(
            LOGGER,
            logging.ERROR,
            "api_request_failed",
            "Unexpected API request failure",
            exc_info=True,
            method=request.method,
            path=request.url.path,
            error_type=type(error).__name__,
        )
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected server error occurred.",
        )

    return application


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(code=code, message=message)
    return JSONResponse(status_code=status_code, content=body.model_dump())
