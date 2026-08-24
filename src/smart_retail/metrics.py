"""Bounded, thread-safe operational metrics without framework dependencies."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from smart_retail.domain.events import CheckoutEventType
from smart_retail.domain.models import CartSnapshot


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """One internally consistent copy of current counters and gauges."""

    frames_processed_total: int
    dropped_frames_total: int
    detections_total: int
    active_tracks: int
    inference_latency_ms: float
    frame_processing_latency_ms: float
    current_fps: float
    checkout_enter_events_total: int
    checkout_exit_events_total: int
    cart_additions_total: int
    cart_removals_total: int
    cart_resets_total: int
    current_cart_items: int
    current_cart_total: int
    uptime_seconds: float
    camera_errors_total: int
    persistence_errors_total: int


class MetricsService:
    """Maintain counters, gauges, and bounded rolling latency averages."""

    def __init__(
        self,
        rolling_window_size: int = 60,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if (
            isinstance(rolling_window_size, bool)
            or not isinstance(rolling_window_size, int)
            or rolling_window_size < 1
        ):
            raise ValueError("Metrics rolling window must be at least 1.")
        self._clock = clock
        self._started_at = clock()
        self._lock = threading.Lock()
        self._inference_latencies: deque[float] = deque(maxlen=rolling_window_size)
        self._frame_latencies: deque[float] = deque(maxlen=rolling_window_size)
        self._frames_processed_total = 0
        self._dropped_frames_total = 0
        self._detections_total = 0
        self._active_tracks = 0
        self._current_fps = 0.0
        self._checkout_enter_events_total = 0
        self._checkout_exit_events_total = 0
        self._cart_additions_total = 0
        self._cart_removals_total = 0
        self._cart_resets_total = 0
        self._current_cart_items = 0
        self._current_cart_total = 0
        self._camera_errors_total = 0
        self._persistence_errors_total = 0

    def record_frame(
        self,
        detection_count: int,
        active_tracks: int,
        inference_latency_ms: float,
        frame_processing_latency_ms: float,
        current_fps: float,
    ) -> None:
        """Record one frame that completed vision and checkout processing."""
        _validate_nonnegative_integer("detection count", detection_count)
        _validate_nonnegative_integer("active tracks", active_tracks)
        _validate_nonnegative("inference latency", inference_latency_ms)
        _validate_nonnegative("frame processing latency", frame_processing_latency_ms)
        _validate_nonnegative("current FPS", current_fps)
        with self._lock:
            self._frames_processed_total += 1
            self._detections_total += detection_count
            self._active_tracks = active_tracks
            self._inference_latencies.append(float(inference_latency_ms))
            self._frame_latencies.append(float(frame_processing_latency_ms))
            self._current_fps = float(current_fps)

    def record_dropped_frame(self) -> None:
        with self._lock:
            self._dropped_frames_total += 1

    def record_checkout_event(self, event_type: CheckoutEventType) -> None:
        if not isinstance(event_type, CheckoutEventType):
            raise TypeError("Checkout event type must be a CheckoutEventType value.")
        with self._lock:
            if event_type is CheckoutEventType.ENTER:
                self._checkout_enter_events_total += 1
            else:
                self._checkout_exit_events_total += 1

    def record_cart_addition(self, snapshot: CartSnapshot) -> None:
        with self._lock:
            self._cart_additions_total += 1
            self._set_cart_gauges(snapshot)

    def record_cart_removal(self, snapshot: CartSnapshot) -> None:
        with self._lock:
            self._cart_removals_total += 1
            self._set_cart_gauges(snapshot)

    def record_cart_reset(self, snapshot: CartSnapshot) -> None:
        with self._lock:
            self._cart_resets_total += 1
            self._set_cart_gauges(snapshot)

    def record_camera_error(self) -> None:
        with self._lock:
            self._camera_errors_total += 1

    def record_persistence_error(self) -> None:
        with self._lock:
            self._persistence_errors_total += 1

    def get_snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                frames_processed_total=self._frames_processed_total,
                dropped_frames_total=self._dropped_frames_total,
                detections_total=self._detections_total,
                active_tracks=self._active_tracks,
                inference_latency_ms=_average(self._inference_latencies),
                frame_processing_latency_ms=_average(self._frame_latencies),
                current_fps=self._current_fps,
                checkout_enter_events_total=self._checkout_enter_events_total,
                checkout_exit_events_total=self._checkout_exit_events_total,
                cart_additions_total=self._cart_additions_total,
                cart_removals_total=self._cart_removals_total,
                cart_resets_total=self._cart_resets_total,
                current_cart_items=self._current_cart_items,
                current_cart_total=self._current_cart_total,
                uptime_seconds=max(0.0, self._clock() - self._started_at),
                camera_errors_total=self._camera_errors_total,
                persistence_errors_total=self._persistence_errors_total,
            )

    def _set_cart_gauges(self, snapshot: CartSnapshot) -> None:
        self._current_cart_items = snapshot.total_quantity
        self._current_cart_total = snapshot.total


def _average(values: deque[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _validate_nonnegative(name: str, value: int | float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Metrics {name} must be a finite nonnegative number.")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Metrics {name} must be a finite nonnegative number.")


def _validate_nonnegative_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Metrics {name} must be a nonnegative integer.")
