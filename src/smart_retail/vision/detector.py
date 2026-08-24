"""YOLO model loading, class resolution, and device selection."""

from __future__ import annotations

import logging
from pathlib import Path

import torch
from ultralytics import YOLO

from smart_retail.infrastructure.logging_config import log_event

LOGGER = logging.getLogger(__name__)


def select_inference_device() -> str:
    """Prefer Apple MPS when correctly available, otherwise CPU."""
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_built() and mps.is_available():
        return "mps"
    return "cpu"


def resolve_inference_device(preference: str) -> str:
    """Resolve an explicit CPU/MPS preference or choose automatically."""
    if preference == "cpu":
        return "cpu"
    if preference == "mps":
        if select_inference_device() == "mps":
            return "mps"
        raise ValueError(
            "MPS was explicitly requested but is not available on this machine."
        )
    if preference == "auto":
        return select_inference_device()
    raise ValueError("Device preference must be one of: auto, mps, cpu.")


class YOLODetector:
    """Own one YOLO model and its configured class mapping."""

    def __init__(
        self,
        model_path: str,
        allowed_classes: tuple[str, ...],
        device_preference: str = "auto",
    ) -> None:
        self.device = resolve_inference_device(device_preference)
        log_event(
            LOGGER,
            logging.INFO,
            "inference_device_selected",
            "Inference device selected",
            preference=device_preference,
            device=self.device,
        )
        log_event(
            LOGGER,
            logging.INFO,
            "model_initializing",
            "Loading object-detection model",
            model=Path(model_path).name,
            device=self.device,
        )
        self.model = YOLO(model_path)
        model_names = self.model.names
        self.class_names = (
            dict(model_names)
            if isinstance(model_names, dict)
            else dict(enumerate(model_names))
        )

        allowed_class_set = set(allowed_classes)
        self.allowed_class_ids = [
            class_id
            for class_id, class_name in self.class_names.items()
            if class_name in allowed_class_set
        ]
        missing_classes = allowed_class_set - set(self.class_names.values())
        if missing_classes:
            missing = ", ".join(sorted(missing_classes))
            raise ValueError(f"Model does not contain configured classes: {missing}")
        log_event(
            LOGGER,
            logging.INFO,
            "model_initialized",
            "Object-detection model loaded",
            model=Path(model_path).name,
            device=self.device,
            allowed_class_count=len(self.allowed_class_ids),
        )

    def move_to(self, device: str) -> None:
        """Move the loaded model and update its active inference device."""
        self.model.to(device)
        self.device = device
        log_event(
            LOGGER,
            logging.INFO,
            "inference_device_changed",
            "Inference device changed",
            device=device,
        )
