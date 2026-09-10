"""FastAPI dependency access to the shared application coordinator."""

from __future__ import annotations

from typing import Annotated, Protocol, cast, runtime_checkable

from fastapi import Depends, Request

from smart_retail.application_state import (
    CartResetResult,
    DemoCartMutationResult,
    SessionHistory,
)
from smart_retail.domain.events import CartEvent
from smart_retail.domain.models import CartSnapshot, CheckoutSession, Product
from smart_retail.health import LivenessSnapshot, ReadinessSnapshot
from smart_retail.metrics import MetricsSnapshot
from smart_retail.realtime.broadcaster import RealtimeSubscription


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

    def subscribe_realtime(self) -> RealtimeSubscription: ...

    def unsubscribe_realtime(self, subscription: RealtimeSubscription) -> None: ...

    def get_realtime_heartbeat_seconds(self) -> float: ...


def get_runtime(request: Request) -> APIRuntime:
    return cast(APIRuntime, request.app.state.runtime)


RuntimeDependency = Annotated[APIRuntime, Depends(get_runtime)]


@runtime_checkable
class DemoAPIRuntime(Protocol):
    """Synthetic commands available only in an explicitly enabled demo runtime."""

    def get_demo_products(self) -> tuple[Product, ...]: ...

    def add_demo_item(self, product_id: str) -> DemoCartMutationResult: ...

    def remove_demo_item(self, product_id: str) -> DemoCartMutationResult: ...


def get_demo_runtime(request: Request) -> DemoAPIRuntime:
    return cast(DemoAPIRuntime, request.app.state.runtime)


DemoRuntimeDependency = Annotated[DemoAPIRuntime, Depends(get_demo_runtime)]
