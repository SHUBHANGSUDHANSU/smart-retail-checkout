"""Bounded thread-safe fan-out without network I/O in publishers."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

from smart_retail.infrastructure.logging_config import log_event
from smart_retail.realtime.models import (
    RealtimeEventType,
    RealtimeMessage,
    RealtimePayload,
)

LOGGER = logging.getLogger(__name__)


class RealtimeClosedError(RuntimeError):
    """Raised when a subscriber is requested after broadcaster shutdown."""


class RealtimeSubscription:
    """One client's private bounded queue."""

    def __init__(self, subscriber_id: int, capacity: int) -> None:
        self.subscriber_id = subscriber_id
        self._queue: queue.Queue[RealtimeMessage] = queue.Queue(maxsize=capacity)
        self._closed = threading.Event()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def get(self, timeout: float) -> RealtimeMessage | None:
        if self.closed:
            return None
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_nowait(self) -> RealtimeMessage:
        return self._queue.get_nowait()

    def _offer(self, message: RealtimeMessage) -> bool:
        if self.closed:
            return False
        try:
            self._queue.put_nowait(message)
            return False
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(message)
            except queue.Full:
                pass
            return True

    def _close(self) -> None:
        self._closed.set()


class RealtimeBroadcaster:
    """Fan out immutable messages through independent bounded queues."""

    def __init__(
        self,
        queue_capacity: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if isinstance(queue_capacity, bool) or queue_capacity < 1:
            raise ValueError("Realtime queue capacity must be at least 1.")
        self._queue_capacity = queue_capacity
        self._clock = clock
        self._lock = threading.Lock()
        self._subscribers: dict[int, RealtimeSubscription] = {}
        self._next_subscriber_id = 1
        self._next_sequence = 1
        self._closed = False

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def subscribe(self) -> RealtimeSubscription:
        with self._lock:
            if self._closed:
                raise RealtimeClosedError("Realtime broadcaster is closed.")
            subscriber_id = self._next_subscriber_id
            self._next_subscriber_id += 1
            subscription = RealtimeSubscription(
                subscriber_id,
                self._queue_capacity,
            )
            self._subscribers[subscriber_id] = subscription
            return subscription

    def unsubscribe(self, subscription: RealtimeSubscription) -> None:
        with self._lock:
            current = self._subscribers.get(subscription.subscriber_id)
            if current is subscription:
                self._subscribers.pop(subscription.subscriber_id, None)
            subscription._close()

    def publish(
        self,
        event_type: RealtimeEventType,
        payload: RealtimePayload,
    ) -> RealtimeMessage:
        with self._lock:
            sequence = self._next_sequence
            self._next_sequence += 1
            subscribers = tuple(self._subscribers.values())
        message = RealtimeMessage(sequence, event_type, self._clock(), payload)
        for subscription in subscribers:
            if subscription._offer(message):
                log_event(
                    LOGGER,
                    logging.WARNING,
                    "realtime.message_dropped",
                    "Slow realtime client dropped its oldest queued message",
                    subscriber_id=subscription.subscriber_id,
                    realtime_event_type=event_type.value,
                    queue_capacity=self._queue_capacity,
                )
        return message

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscriptions = tuple(self._subscribers.values())
            self._subscribers.clear()
        for subscription in subscriptions:
            subscription._close()
