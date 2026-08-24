"""Ultralytics ByteTrack adapter and result normalization."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import torch

from smart_retail.domain.models import TrackedObject
from smart_retail.infrastructure.logging_config import log_event
from smart_retail.vision.detector import YOLODetector


class ByteTracker:
    """Run YOLO detection with persistent ByteTrack association."""

    def __init__(
        self,
        detector: YOLODetector,
        confidence_threshold: float,
        tracking_confidence_threshold: float,
        iou_threshold: float,
        image_size: int,
        tracker_config_path: str | Path,
        persist_tracks: bool,
        logger: logging.Logger | None = None,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("Confidence threshold must be between 0.0 and 1.0.")
        if not 0.0 <= tracking_confidence_threshold <= confidence_threshold:
            raise ValueError(
                "Tracking confidence threshold must be between 0.0 and the "
                "display confidence threshold."
            )
        if not 0.0 <= iou_threshold <= 1.0:
            raise ValueError("IoU threshold must be between 0.0 and 1.0.")
        self.detector = detector
        self.confidence_threshold = confidence_threshold
        self.tracking_confidence_threshold = tracking_confidence_threshold
        self.iou_threshold = iou_threshold
        self.image_size = image_size
        self.tracker_config_path = str(tracker_config_path)
        self.persist_tracks = persist_tracks
        self.logger = logger or logging.getLogger(__name__)
        log_event(
            self.logger,
            logging.INFO,
            "tracker_initialized",
            "ByteTrack initialized",
            tracker_config=Path(self.tracker_config_path).name,
            persist=self.persist_tracks,
            confidence_threshold=self.confidence_threshold,
            association_threshold=self.tracking_confidence_threshold,
        )

    @property
    def device(self) -> str:
        return self.detector.device

    def track(self, frame: np.ndarray) -> list[TrackedObject]:
        """Return trusted domain observations from one sequential frame."""
        try:
            result = self._run_tracking(frame)
        except Exception as error:
            if self.device != "mps":
                raise
            log_event(
                self.logger,
                logging.WARNING,
                "inference_device_fallback",
                "MPS inference failed; retrying on CPU",
                from_device="mps",
                to_device="cpu",
                error_type=type(error).__name__,
                reason=str(error)[:240],
            )
            self.detector.move_to("cpu")
            result = self._run_tracking(frame)

        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []

        coordinates = boxes.xyxy.detach().cpu().tolist()
        class_ids = boxes.cls.detach().to(dtype=torch.int64).cpu().tolist()
        confidences = boxes.conf.detach().cpu().tolist()
        if boxes.id is None:
            track_ids: list[int | None] = [None] * len(boxes)
        else:
            track_ids = [int(track_id) for track_id in boxes.id.detach().cpu().tolist()]

        tracked_objects: list[TrackedObject] = []
        for box, class_id, confidence, track_id in zip(
            coordinates,
            class_ids,
            confidences,
            track_ids,
            strict=True,
        ):
            if confidence < self.confidence_threshold:
                continue
            tracked_objects.append(
                TrackedObject(
                    track_id=track_id,
                    class_name=self.detector.class_names[class_id],
                    confidence=confidence,
                    bbox=tuple(round(value) for value in box),
                )
            )
        return tracked_objects

    def _run_tracking(self, frame: np.ndarray):
        return self.detector.model.track(
            source=frame,
            classes=self.detector.allowed_class_ids,
            conf=self.tracking_confidence_threshold,
            iou=self.iou_threshold,
            imgsz=self.image_size,
            device=self.device,
            tracker=self.tracker_config_path,
            persist=self.persist_tracks,
            verbose=False,
        )[0]
