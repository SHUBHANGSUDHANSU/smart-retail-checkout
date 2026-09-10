"""Application-level publication policy over the realtime broadcaster."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from smart_retail.domain.models import CartSnapshot
from smart_retail.metrics import MetricsSnapshot
from smart_retail.realtime.broadcaster import (
    RealtimeBroadcaster,
    RealtimeSubscription,
)
from smart_retail.realtime.models import (
    RealtimeCheckoutActivity,
    RealtimeEventType,
    RealtimeMessage,
)


class RealtimePublisher:
    """Publish business snapshots and throttle high-frequency metrics."""

    def __init__(
        self,
        broadcaster: RealtimeBroadcaster,
        metrics_interval_seconds: float,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if metrics_interval_seconds <= 0:
            raise ValueError("Realtime metrics interval must be positive.")
        self._broadcaster = broadcaster
        self._metrics_interval_seconds = metrics_interval_seconds
        self._monotonic_clock = monotonic_clock
        self._metrics_lock = threading.Lock()
        self._last_metrics_at: float | None = None

    def subscribe(self) -> RealtimeSubscription:
        return self._broadcaster.subscribe()

    def unsubscribe(self, subscription: RealtimeSubscription) -> None:
        self._broadcaster.unsubscribe(subscription)

    def publish_cart(self, snapshot: CartSnapshot) -> RealtimeMessage:
        return self._broadcaster.publish(RealtimeEventType.CART_UPDATED, snapshot)

    def publish_checkout_event(
        self,
        activity: RealtimeCheckoutActivity,
    ) -> RealtimeMessage:
        return self._broadcaster.publish(RealtimeEventType.CHECKOUT_EVENT, activity)

    def publish_metrics_if_due(self, snapshot: MetricsSnapshot) -> bool:
        now = self._monotonic_clock()
        with self._metrics_lock:
            if (
                self._last_metrics_at is not None
                and now - self._last_metrics_at < self._metrics_interval_seconds
            ):
                return False
            self._last_metrics_at = now
        self._broadcaster.publish(RealtimeEventType.METRICS_UPDATED, snapshot)
        return True

    def close(self) -> None:
        self._broadcaster.close()
