"""FastAPI dependency access to the shared application coordinator."""

from __future__ import annotations

from typing import Annotated, Protocol, cast, runtime_checkable

from fastapi import Depends, Request

from smart_retail.application_state import CartResetResult, SessionHistory
from smart_retail.domain.events import CartEvent
from smart_retail.domain.models import CartSnapshot, CheckoutSession
from smart_retail.health import LivenessSnapshot, ReadinessSnapshot
from smart_retail.metrics import MetricsSnapshot


@runtime_checkable
class APIRuntime(Protocol):
    """Business-state operations consumed by the HTTP presentation layer."""

    def get_cart_snapshot(self) -> CartSnapshot: ...

    def reset_checkout(self, source: str) -> CartResetResult: ...

    def get_liveness_snapshot(self) -> LivenessSnapshot: ...

    def get_readiness_snapshot(self) -> ReadinessSnapshot: ...

    def get_metrics_snapshot(self) -> MetricsSnapshot: ...

    def get_recent_cart_events(self, limit: int) -> list[CartEvent]: ...

    def get_recent_checkout_sessions(self, limit: int) -> list[CheckoutSession]: ...

    def get_checkout_session_history(
        self, session_id: int
    ) -> SessionHistory | None: ...


def get_runtime(request: Request) -> APIRuntime:
    return cast(APIRuntime, request.app.state.runtime)


RuntimeDependency = Annotated[APIRuntime, Depends(get_runtime)]
