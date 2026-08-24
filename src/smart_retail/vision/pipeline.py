"""Timed vision pipeline consumed by application orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from smart_retail.domain.models import TrackedObject
from smart_retail.vision.tracker import ByteTracker


@dataclass(frozen=True, slots=True)
class VisionResult:
    tracked_objects: tuple[TrackedObject, ...]
    inference_time_ms: float


class VisionPipeline:
    """Measure and delegate one frame to the configured tracker."""

    def __init__(
        self,
        tracker: ByteTracker,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.tracker = tracker
        self._clock = clock

    @property
    def device(self) -> str:
        return self.tracker.device

    def process(self, frame: np.ndarray) -> VisionResult:
        started_at = self._clock()
        tracked_objects = self.tracker.track(frame)
        elapsed_ms = (self._clock() - started_at) * 1000.0
        return VisionResult(tuple(tracked_objects), elapsed_ms)
