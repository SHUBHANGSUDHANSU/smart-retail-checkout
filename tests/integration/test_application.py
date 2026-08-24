"""Tests for camera infrastructure and application resource cleanup."""

import io
import json
import logging
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from smart_retail.app import SmartRetailApplication, build_application, main
from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutUpdate
from smart_retail.config import CameraConfig, load_config
from smart_retail.domain.events import CheckoutEvent, CheckoutEventType
from smart_retail.domain.models import TrackedObject
from smart_retail.health import HealthComponent, HealthService
from smart_retail.infrastructure.camera import CameraError, OpenCVCamera
from smart_retail.infrastructure.logging_config import JsonEventFormatter
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.metrics import MetricsService
from smart_retail.vision.pipeline import VisionResult


def initialized_health(database_enabled: bool) -> HealthService:
    health = HealthService(database_enabled=database_enabled)
    health.mark_ready(HealthComponent.CORE_SERVICES)
    health.mark_ready(HealthComponent.MODEL)
    if database_enabled:
        health.mark_ready(HealthComponent.DATABASE)
    return health


class CameraTests(unittest.TestCase):
    def test_each_failed_read_attempt_invokes_dropped_frame_callback(self) -> None:
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.read.side_effect = [(False, None), (True, np.zeros((2, 2, 3)))]
        dropped_frame = MagicMock()
        camera = OpenCVCamera(
            CameraConfig(read_max_attempts=2, read_retry_delay_seconds=0.0),
            capture_factory=MagicMock(return_value=capture),
            sleep=MagicMock(),
            on_dropped_frame=dropped_frame,
        )

        camera.open()
        camera.read()

        dropped_frame.assert_called_once_with()

    def test_transient_read_failure_recovers_and_mirrors(self) -> None:
        source_frame = np.arange(18, dtype=np.uint8).reshape((2, 3, 3))
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.read.side_effect = [(False, None), (True, source_frame)]
        capture_factory = MagicMock(return_value=capture)
        camera = OpenCVCamera(
            CameraConfig(
                read_max_attempts=3,
                read_retry_delay_seconds=0.0,
                mirror=True,
            ),
            capture_factory=capture_factory,
            sleep=MagicMock(),
        )

        camera.open()
        frame = camera.read()

        capture_factory.assert_called_once_with(0, cv2.CAP_AVFOUNDATION)
        capture.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        capture.set.assert_any_call(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.assertEqual(capture.read.call_count, 2)
        np.testing.assert_array_equal(frame, cv2.flip(source_frame, 1))

    def test_persistent_read_failure_raises_useful_error(self) -> None:
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.read.return_value = (False, None)
        camera = OpenCVCamera(
            CameraConfig(read_max_attempts=3, read_retry_delay_seconds=0.0),
            capture_factory=MagicMock(return_value=capture),
            sleep=MagicMock(),
        )
        camera.open()

        with self.assertRaisesRegex(CameraError, "after 3 attempts"):
            camera.read()

        self.assertEqual(capture.read.call_count, 3)

    def test_initialization_failure_releases_capture(self) -> None:
        capture = MagicMock()
        capture.isOpened.return_value = False
        camera = OpenCVCamera(
            CameraConfig(),
            capture_factory=MagicMock(return_value=capture),
        )

        with self.assertRaisesRegex(CameraError, "Camera permission"):
            camera.open()

        capture.release.assert_called_once()


class ApplicationCleanupTests(unittest.TestCase):
    def test_composition_failure_closes_initialized_repository(self) -> None:
        config = load_config({"SMART_RETAIL_API_ENABLED": "false"})
        repository = MagicMock()
        with (
            patch(
                "smart_retail.app.SQLiteCheckoutRepository",
                return_value=repository,
            ),
            patch(
                "smart_retail.app.YOLODetector",
                side_effect=RuntimeError("model failed"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "model failed"):
                build_application(config, logging.getLogger("test.composition"))

        repository.initialize.assert_called_once()
        repository.close.assert_called_once_with()

    def test_keyboard_interrupt_during_composition_closes_repository(self) -> None:
        config = load_config({"SMART_RETAIL_API_ENABLED": "false"})
        repository = MagicMock()
        with (
            patch(
                "smart_retail.app.SQLiteCheckoutRepository",
                return_value=repository,
            ),
            patch("smart_retail.app.YOLODetector", side_effect=KeyboardInterrupt),
        ):
            with self.assertRaises(KeyboardInterrupt):
                build_application(config, logging.getLogger("test.interrupt"))

        repository.close.assert_called_once_with()

    def test_main_handles_keyboard_interrupt_during_startup(self) -> None:
        config = load_config({"SMART_RETAIL_API_ENABLED": "false"})
        logger = logging.Logger("test.main.interrupt")
        logger.addHandler(logging.NullHandler())
        with (
            patch("smart_retail.app.load_config", return_value=config),
            patch("smart_retail.app.configure_logging", return_value=logger),
            patch("smart_retail.app.build_application", side_effect=KeyboardInterrupt),
        ):
            self.assertEqual(main(), 0)

    def test_quit_releases_camera_and_closes_ui(self) -> None:
        config = load_config({})
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera = MagicMock()
        camera.read.return_value = frame
        vision = MagicMock()
        vision.device = "cpu"
        vision.process.return_value = VisionResult((), 5.0)
        event_engine = MagicMock()
        event_engine.process_frame.return_value = CheckoutUpdate((), ())
        ui = MagicMock()
        ui.poll_key.return_value = ord("q")
        api_server = MagicMock()
        application = SmartRetailApplication(
            config=config,
            logger=logging.getLogger("test.application"),
            camera=camera,
            vision=vision,
            event_engine=event_engine,
            cart=MagicMock(),
            ui=ui,
            health=initialized_health(config.database.enabled),
            api_server=api_server,
        )

        self.assertEqual(application.run(), 0)

        camera.open.assert_called_once()
        camera.release.assert_called_once()
        ui.close.assert_called_once()
        api_server.start.assert_called_once_with()
        api_server.stop.assert_called_once_with()
        self.assertEqual(
            application.health.get_readiness().application_state.value,
            "stopped",
        )


class ApplicationObservabilityTests(unittest.TestCase):
    def test_run_records_completed_frame_metrics(self) -> None:
        config = load_config({"SMART_RETAIL_API_ENABLED": "false"})
        tracked = TrackedObject(7, "bottle", 0.9, (10, 10, 50, 50))
        camera = MagicMock()
        camera.read.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        vision = MagicMock(device="cpu")
        vision.process.return_value = VisionResult((tracked,), 8.0)
        event_engine = MagicMock()
        event_engine.process_frame.return_value = CheckoutUpdate((), ())
        ui = MagicMock()
        ui.poll_key.return_value = ord("q")
        metrics = MetricsService()
        application = SmartRetailApplication(
            config=config,
            logger=logging.getLogger("test.application.metrics"),
            camera=camera,
            vision=vision,
            event_engine=event_engine,
            cart=CartService(load_product_catalog(config.products_config_path)),
            ui=ui,
            health=initialized_health(config.database.enabled),
            metrics=metrics,
        )

        self.assertEqual(application.run(), 0)

        snapshot = metrics.get_snapshot()
        self.assertEqual(snapshot.frames_processed_total, 1)
        self.assertEqual(snapshot.detections_total, 1)
        self.assertEqual(snapshot.active_tracks, 1)
        self.assertEqual(snapshot.inference_latency_ms, 8.0)
        self.assertGreaterEqual(snapshot.frame_processing_latency_ms, 0.0)
        self.assertGreaterEqual(snapshot.current_fps, 0.0)

    def test_checkout_metrics_distinguish_events_from_cart_mutations(self) -> None:
        config = load_config({})
        metrics = MetricsService()
        application = SmartRetailApplication(
            config=config,
            logger=logging.getLogger("test.application.business_metrics"),
            camera=MagicMock(),
            vision=MagicMock(),
            event_engine=MagicMock(),
            cart=CartService(load_product_catalog(config.products_config_path)),
            ui=MagicMock(),
            health=initialized_health(config.database.enabled),
            metrics=metrics,
        )
        enter = CheckoutEvent(CheckoutEventType.ENTER, 7, "bottle", 1.0)

        application._apply_checkout_event(enter)
        application._apply_checkout_event(enter)
        application._apply_checkout_event(
            CheckoutEvent(CheckoutEventType.EXIT, 7, "bottle", 2.0)
        )
        application.reset_checkout(source="opencv")

        snapshot = metrics.get_snapshot()
        self.assertEqual(snapshot.checkout_enter_events_total, 2)
        self.assertEqual(snapshot.checkout_exit_events_total, 1)
        self.assertEqual(snapshot.cart_additions_total, 1)
        self.assertEqual(snapshot.cart_removals_total, 1)
        self.assertEqual(snapshot.cart_resets_total, 1)
        self.assertEqual(snapshot.current_cart_items, 0)
        self.assertEqual(snapshot.current_cart_total, 0)

    def test_checkout_and_cart_events_have_business_fields(self) -> None:
        config = load_config({})
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonEventFormatter())
        logger = logging.Logger("test.application.events", level=logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        ui = MagicMock()
        application = SmartRetailApplication(
            config=config,
            logger=logger,
            camera=MagicMock(),
            vision=MagicMock(),
            event_engine=MagicMock(),
            cart=CartService(load_product_catalog(config.products_config_path)),
            ui=ui,
            health=initialized_health(config.database.enabled),
        )

        application._apply_checkout_event(
            CheckoutEvent(
                event_type=CheckoutEventType.ENTER,
                track_id=14,
                product_class="bottle",
                timestamp=123.5,
            )
        )

        payloads = [json.loads(line) for line in stream.getvalue().splitlines()]
        checkout_event, cart_event = payloads
        self.assertEqual(checkout_event["event"], "checkout_enter")
        self.assertEqual(checkout_event["track_id"], 14)
        self.assertEqual(cart_event["event"], "cart_item_added")
        self.assertEqual(cart_event["product"], "Water Bottle")
        self.assertEqual(cart_event["quantity"], 1)
        self.assertEqual(cart_event["cart_total"], 40)
        ui.show_notification.assert_called_once_with("- Water Bottle added", "add")


if __name__ == "__main__":
    unittest.main()
