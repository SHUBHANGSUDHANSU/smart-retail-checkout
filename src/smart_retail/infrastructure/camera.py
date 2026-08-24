"""OpenCV webcam ownership and retry behavior."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import cv2

from smart_retail.config import CameraConfig
from smart_retail.infrastructure.logging_config import log_event

LOGGER = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Raised when the webcam cannot initialize or produce a frame."""


class OpenCVCamera:
    """Own an OpenCV capture and guarantee idempotent cleanup."""

    def __init__(
        self,
        config: CameraConfig,
        capture_factory: Callable[..., Any] = cv2.VideoCapture,
        sleep: Callable[[float], None] = time.sleep,
        on_dropped_frame: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self._capture_factory = capture_factory
        self._sleep = sleep
        self._on_dropped_frame = on_dropped_frame
        self._capture: Any | None = None

    def open(self) -> None:
        """Open the configured macOS camera or raise a useful error."""
        log_event(
            LOGGER,
            logging.INFO,
            "camera_initializing",
            "Initializing camera",
            camera_index=self.config.camera_index,
            requested_width=self.config.width,
            requested_height=self.config.height,
        )
        self._capture = self._capture_factory(
            self.config.camera_index,
            cv2.CAP_AVFOUNDATION,
        )
        if self._capture.isOpened():
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            log_event(
                LOGGER,
                logging.INFO,
                "camera_initialized",
                "Camera initialized",
                camera_index=self.config.camera_index,
            )
            return
        log_event(
            LOGGER,
            logging.ERROR,
            "camera_initialization_failed",
            "Camera initialization failed",
            camera_index=self.config.camera_index,
        )
        self.release()
        raise CameraError(
            f"Could not open webcam at index {self.config.camera_index}. "
            "Check that the "
            "camera is connected and that this terminal or IDE has Camera "
            "permission in macOS Privacy & Security settings."
        )

    def read(self):
        """Read and optionally mirror a frame, tolerating brief failures."""
        if self._capture is None:
            log_event(
                LOGGER,
                logging.ERROR,
                "camera_read_before_open",
                "Camera read requested before initialization",
                camera_index=self.config.camera_index,
            )
            raise CameraError("Camera must be opened before reading frames.")

        for attempt in range(self.config.read_max_attempts):
            frame_read, frame = self._capture.read()
            if frame_read and frame is not None:
                if attempt:
                    log_event(
                        LOGGER,
                        logging.WARNING,
                        "camera_read_recovered",
                        "Camera frame reads recovered",
                        camera_index=self.config.camera_index,
                        failed_attempts=attempt,
                    )
                return cv2.flip(frame, 1) if self.config.mirror else frame
            if self._on_dropped_frame is not None:
                self._on_dropped_frame()
            log_event(
                LOGGER,
                logging.DEBUG,
                "camera_read_retry",
                "Camera frame read failed; retrying",
                camera_index=self.config.camera_index,
                attempt=attempt + 1,
                max_attempts=self.config.read_max_attempts,
            )
            if attempt < self.config.read_max_attempts - 1:
                self._sleep(self.config.read_retry_delay_seconds)

        log_event(
            LOGGER,
            logging.ERROR,
            "camera_read_failed",
            "Camera frame reads failed after retries",
            camera_index=self.config.camera_index,
            attempts=self.config.read_max_attempts,
        )
        raise CameraError(
            "The webcam opened, but frames could not be read after "
            f"{self.config.read_max_attempts} attempts. Check camera permissions "
            "and close other apps using the camera."
        )

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            log_event(
                LOGGER,
                logging.INFO,
                "camera_released",
                "Camera released",
                camera_index=self.config.camera_index,
            )
