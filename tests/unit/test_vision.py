"""Tests for ByteTrack normalization and the timed vision pipeline."""

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import torch
from ultralytics.engine.results import Boxes

from smart_retail.vision.detector import (
    resolve_inference_device,
    select_inference_device,
)
from smart_retail.vision.pipeline import VisionPipeline
from smart_retail.vision.tracker import ByteTracker


class ByteTrackerTests(unittest.TestCase):
    def make_tracker(self, box_data: torch.Tensor) -> ByteTracker:
        detector = SimpleNamespace(
            device="cpu",
            class_names={39: "bottle", 41: "cup"},
            allowed_class_ids=[39, 41],
            model=MagicMock(),
        )
        tracker = ByteTracker(
            detector=detector,
            confidence_threshold=0.45,
            tracking_confidence_threshold=0.10,
            iou_threshold=0.70,
            image_size=640,
            tracker_config_path="configs/bytetrack_retail.yaml",
            persist_tracks=True,
            logger=logging.getLogger("test.tracker"),
        )
        result = SimpleNamespace(boxes=Boxes(box_data, orig_shape=(480, 640)))
        tracker._run_tracking = MagicMock(return_value=result)
        return tracker

    def test_empty_tracking_result_returns_empty_list(self) -> None:
        tracker = self.make_tracker(torch.empty((0, 6)))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertEqual(tracker.track(frame), [])

    def test_missing_tracking_ids_are_safe(self) -> None:
        tracker = self.make_tracker(
            torch.tensor([[10, 20, 110, 220, 0.91, 39]], dtype=torch.float32)
        )
        tracked_objects = tracker.track(np.zeros((480, 640, 3), dtype=np.uint8))

        self.assertEqual(len(tracked_objects), 1)
        self.assertIsNone(tracked_objects[0].track_id)
        self.assertEqual(tracked_objects[0].centroid, (60.0, 120.0))

    def test_low_confidence_track_updates_are_not_displayed(self) -> None:
        tracker = self.make_tracker(
            torch.tensor(
                [
                    [10, 20, 110, 220, 4, 0.20, 39],
                    [200, 100, 300, 300, 9, 0.84, 41],
                ],
                dtype=torch.float32,
            )
        )
        tracked_objects = tracker.track(np.zeros((480, 640, 3), dtype=np.uint8))

        self.assertEqual([item.track_id for item in tracked_objects], [9])

    def test_tracking_uses_low_association_threshold(self) -> None:
        detector = SimpleNamespace(
            device="cpu",
            class_names={39: "bottle", 41: "cup"},
            allowed_class_ids=[39, 41],
            model=MagicMock(),
        )
        expected_result = object()
        detector.model.track.return_value = [expected_result]
        tracker = ByteTracker(
            detector,
            confidence_threshold=0.45,
            tracking_confidence_threshold=0.10,
            iou_threshold=0.70,
            image_size=640,
            tracker_config_path="configs/bytetrack_retail.yaml",
            persist_tracks=True,
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        self.assertIs(tracker._run_tracking(frame), expected_result)
        detector.model.track.assert_called_once_with(
            source=frame,
            classes=[39, 41],
            conf=0.10,
            iou=0.70,
            imgsz=640,
            device="cpu",
            tracker="configs/bytetrack_retail.yaml",
            persist=True,
            verbose=False,
        )

    def test_mps_runtime_failure_retries_on_cpu(self) -> None:
        detector = SimpleNamespace(
            device="mps",
            class_names={39: "bottle"},
            allowed_class_ids=[39],
            model=MagicMock(),
        )

        def move_to(device: str) -> None:
            detector.device = device

        detector.move_to = MagicMock(side_effect=move_to)
        tracker = ByteTracker(
            detector,
            confidence_threshold=0.45,
            tracking_confidence_threshold=0.10,
            iou_threshold=0.70,
            image_size=640,
            tracker_config_path="configs/bytetrack_retail.yaml",
            persist_tracks=True,
            logger=MagicMock(),
        )
        empty_result = SimpleNamespace(
            boxes=Boxes(torch.empty((0, 6)), orig_shape=(480, 640))
        )
        tracker._run_tracking = MagicMock(
            side_effect=[RuntimeError("unsupported MPS operation"), empty_result]
        )

        self.assertEqual(
            tracker.track(np.zeros((480, 640, 3), dtype=np.uint8)),
            [],
        )
        self.assertEqual(tracker.device, "cpu")
        detector.move_to.assert_called_once_with("cpu")
        self.assertEqual(tracker._run_tracking.call_count, 2)

    def test_device_selection_falls_back_when_mps_is_unavailable(self) -> None:
        unavailable_mps = SimpleNamespace(
            is_built=lambda: True,
            is_available=lambda: False,
        )
        with patch(
            "smart_retail.vision.detector.torch.backends.mps",
            unavailable_mps,
        ):
            self.assertEqual(select_inference_device(), "cpu")

    def test_explicit_unavailable_mps_is_not_silently_accepted(self) -> None:
        with patch(
            "smart_retail.vision.detector.select_inference_device",
            return_value="cpu",
        ):
            with self.assertRaisesRegex(ValueError, "explicitly requested"):
                resolve_inference_device("mps")

    def test_pipeline_reports_inference_time(self) -> None:
        tracker = MagicMock()
        tracker.device = "cpu"
        tracker.track.return_value = []
        clock_values = iter((10.0, 10.025))
        pipeline = VisionPipeline(tracker, clock=lambda: next(clock_values))

        result = pipeline.process(np.zeros((10, 10, 3), dtype=np.uint8))

        self.assertEqual(result.tracked_objects, ())
        self.assertAlmostEqual(result.inference_time_ms, 25.0)


if __name__ == "__main__":
    unittest.main()
