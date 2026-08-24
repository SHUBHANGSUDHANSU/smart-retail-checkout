"""Persisted checkout-session history routes."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from smart_retail.api.dependencies import RuntimeDependency
from smart_retail.api.errors import ResourceNotFoundError
from smart_retail.api.models import (
    CartEventResponse,
    CheckoutSessionDetailResponse,
    CheckoutSessionResponse,
    ErrorResponse,
    RecentSessionsResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get(
    "",
    response_model=RecentSessionsResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Persistence is unavailable",
        }
    },
)
def get_recent_sessions(
    runtime: RuntimeDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RecentSessionsResponse:
    sessions = runtime.get_recent_checkout_sessions(limit)
    return RecentSessionsResponse(
        sessions=[CheckoutSessionResponse.from_domain(item) for item in sessions],
        limit=limit,
    )


@router.get(
    "/{session_id}",
    response_model=CheckoutSessionDetailResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Checkout session was not found",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Persistence is unavailable",
        },
    },
)
def get_session(
    runtime: RuntimeDependency,
    session_id: Annotated[int, Path(ge=1)],
) -> CheckoutSessionDetailResponse:
    history = runtime.get_checkout_session_history(session_id)
    if history is None:
        raise ResourceNotFoundError(
            "session_not_found",
            f"Checkout session {session_id} was not found.",
        )
    session = CheckoutSessionResponse.from_domain(history.session)
    return CheckoutSessionDetailResponse(
        **session.model_dump(),
        events=[CartEventResponse.from_domain(event) for event in history.events],
    )
