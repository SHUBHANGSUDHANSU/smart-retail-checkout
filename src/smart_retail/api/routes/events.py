"""Persisted checkout-event history routes."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from smart_retail.api.dependencies import RuntimeDependency
from smart_retail.api.models import (
    CartEventResponse,
    ErrorResponse,
    RecentEventsResponse,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "",
    response_model=RecentEventsResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Persistence is unavailable",
        }
    },
)
def get_recent_events(
    runtime: RuntimeDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RecentEventsResponse:
    events = runtime.get_recent_cart_events(limit)
    return RecentEventsResponse(
        events=[CartEventResponse.from_domain(event) for event in events],
        limit=limit,
    )
