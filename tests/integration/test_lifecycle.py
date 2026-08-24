"""Deterministic application startup and shutdown tests."""

import logging
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import numpy as np

from smart_retail.api.server import APIServerError
from smart_retail.app import SmartRetailApplication
from smart_retail.application_state import ApplicationState
from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutUpdate
from smart_retail.config import load_config
from smart_retail.domain.models import CheckoutSession
from smart_retail.health import HealthComponent, HealthService
from smart_retail.infrastructure.camera import CameraError
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.infrastructure.sqlite_repository import PersistenceError
from smart_retail.vision.pipeline import VisionResult


def quiet_logger() -> logging.Logger:
    logger = logging.Logger("test.lifecycle")
    logger.propagate = False
    logger.addHandler(logging.NullHandler())
    return logger


def initialized_health(database_enabled: bool) -> HealthService:
    health = HealthService(database_enabled=database_enabled)
    health.mark_ready(HealthComponent.CORE_SERVICES)
    health.mark_ready(HealthComponent.MODEL)
    if database_enabled:
        health.mark_ready(HealthComponent.DATABASE)
    return health


def make_application(order: list[str]) -> SmartRetailApplication:
    config = load_config({"SMART_RETAIL_API_ENABLED": "false"})
    products = load_product_catalog(config.products_config_path)
    repository = MagicMock()
    repository.create_session.return_value = CheckoutSession(7, 100.0, None, None)
    repository.close_session.side_effect = lambda *args, **kwargs: order.append(
        "session"
    )
    repository.close.side_effect = lambda: order.append("database")
    camera = MagicMock()
    camera.read.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    camera.release.side_effect = lambda: order.append("camera")
    ui = MagicMock()
    ui.poll_key.return_value = ord("q")
    ui.close.side_effect = lambda: order.append("ui")
    api_server = MagicMock()
    api_server.stop.side_effect = lambda: order.append("api")
    return SmartRetailApplication(
        config=config,
        logger=quiet_logger(),
        camera=camera,
        vision=MagicMock(
            device="cpu",
            process=MagicMock(return_value=VisionResult((), 5.0)),
        ),
        event_engine=MagicMock(
            process_frame=MagicMock(return_value=CheckoutUpdate((), ())),
        ),
        cart=CartService(products),
        ui=ui,
        health=initialized_health(config.database.enabled),
        persistence=repository,
        persistence_session_id=7,
        api_server=api_server,
    )


class ObservableRunFinished:
    """Expose when shutdown starts waiting without changing application code."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.wait_entered = threading.Event()

    def clear(self) -> None:
        self._event.clear()

    def set(self) -> None:
        self._event.set()

    def wait(self, timeout: float | None = None) -> bool:
        self.wait_entered.set()
        wait_timeout = 2.0 if timeout is None else timeout
        if not self._event.wait(timeout=wait_timeout):
            raise TimeoutError("run loop did not finish before shutdown timeout")
        return True


class ApplicationLifecycleTests(unittest.TestCase):
    def test_external_shutdown_waits_for_frame_loop_and_stops_next_frame(self) -> None:
        order: list[str] = []
        application = make_application(order)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        application.camera.read.side_effect = [
            frame,
            CameraError("second frame should not be requested"),
        ]
        vision_entered = threading.Event()
        release_vision = threading.Event()

        def process_frame(_frame) -> VisionResult:
            vision_entered.set()
            self.assertTrue(release_vision.wait(timeout=2.0))
            return VisionResult((), 5.0)

        application.vision.process.side_effect = process_frame
        application.ui.poll_key.return_value = -1
        run_finished = ObservableRunFinished()
        application._run_finished = run_finished

        with ThreadPoolExecutor(max_workers=2) as executor:
            run_future = executor.submit(application.run)
            self.assertTrue(vision_entered.wait(timeout=1.0))
            shutdown_future = executor.submit(application.shutdown, "external_request")
            try:
                self.assertTrue(run_finished.wait_entered.wait(timeout=1.0))
                self.assertEqual(order, [])
            finally:
                release_vision.set()

            self.assertEqual(run_future.result(timeout=2.0), 0)
            self.assertTrue(shutdown_future.result(timeout=2.0))

        self.assertTrue(run_future.done())
        self.assertTrue(shutdown_future.done())
        self.assertEqual(order, ["api", "session", "camera", "ui", "database"])

    def test_failed_api_stop_is_retried_without_repeating_other_cleanup(self) -> None:
        order: list[str] = []
        application = make_application(order)
        attempts = 0

        def stop_api() -> None:
            nonlocal attempts
            attempts += 1
            order.append("api")
            if attempts == 1:
                raise APIServerError("FastAPI server did not stop")

        application.api_server.stop.side_effect = stop_api

        self.assertFalse(application.shutdown("first"))
        self.assertEqual(
            application.get_readiness_snapshot().application_state,
            ApplicationState.STOPPING,
        )
        self.assertTrue(application.shutdown("retry"))
        self.assertEqual(
            order,
            ["api", "api", "session", "camera", "ui", "database"],
        )

    def test_failed_session_close_retains_repository_and_retries_before_database(
        self,
    ) -> None:
        order: list[str] = []
        application = make_application(order)
        attempts = 0

        def close_session(*args, **kwargs) -> None:
            nonlocal attempts
            attempts += 1
            order.append("session")
            if attempts == 1:
                raise PersistenceError("database locked")

        application.persistence.close_session.side_effect = close_session
        repository = application.persistence

        self.assertFalse(application.shutdown("first"))
        self.assertEqual(order, ["api", "session", "camera", "ui"])
        self.assertEqual(application.persistence_session_id, 7)
        self.assertIs(application.persistence, repository)

        self.assertTrue(application.shutdown("retry"))
        self.assertEqual(
            order,
            ["api", "session", "camera", "ui", "session", "database"],
        )
        self.assertIsNone(application.persistence_session_id)
        self.assertIsNone(application.persistence)

    def test_api_start_failure_retains_adapter_for_shutdown_retry(self) -> None:
        order: list[str] = []
        application = make_application(order)
        api_server = application.api_server
        api_server.start.side_effect = APIServerError("startup timed out")

        application._start_api_server()

        self.assertIs(application.api_server, api_server)

    def test_shutdown_is_ordered_and_idempotent(self) -> None:
        order: list[str] = []
        application = make_application(order)

        first = application.shutdown("user_quit", frames_processed=12)
        second = application.shutdown("repeated", frames_processed=99)

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(order, ["api", "session", "camera", "ui", "database"])
        self.assertEqual(
            application.get_readiness_snapshot().application_state,
            ApplicationState.STOPPED,
        )

    def test_cleanup_failure_does_not_skip_later_resources(self) -> None:
        order: list[str] = []
        application = make_application(order)

        def fail_camera_release() -> None:
            order.append("camera")
            raise RuntimeError("release failed")

        application.camera.release.side_effect = fail_camera_release

        self.assertFalse(application.shutdown("unexpected_error"))
        self.assertEqual(order, ["api", "session", "camera", "ui", "database"])

    def test_keyboard_interrupt_performs_clean_shutdown(self) -> None:
        order: list[str] = []
        application = make_application(order)
        application.camera.read.side_effect = KeyboardInterrupt

        self.assertEqual(application.run(), 0)
        self.assertEqual(order, ["api", "session", "camera", "ui", "database"])

    def test_camera_initialization_failure_closes_started_session(self) -> None:
        order: list[str] = []
        application = make_application(order)
        application.camera.open.side_effect = CameraError("camera unavailable")

        self.assertEqual(application.run(), 1)
        self.assertEqual(order, ["api", "session", "camera", "ui", "database"])
        self.assertEqual(
            application.get_metrics_snapshot().camera_errors_total,
            1,
        )

    def test_unexpected_vision_failure_preserves_error_exit(self) -> None:
        order: list[str] = []
        application = make_application(order)
        application.vision.process.side_effect = RuntimeError("vision failed")

        def fail_camera_release() -> None:
            order.append("camera")
            raise RuntimeError("release failed")

        application.camera.release.side_effect = fail_camera_release

        self.assertEqual(application.run(), 1)
        self.assertEqual(order, ["api", "session", "camera", "ui", "database"])

    def test_normal_exit_reports_cleanup_failure(self) -> None:
        order: list[str] = []
        application = make_application(order)

        def fail_ui_close() -> None:
            order.append("ui")
            raise RuntimeError("window close failed")

        application.ui.close.side_effect = fail_ui_close

        self.assertEqual(application.run(), 1)
        self.assertEqual(order, ["api", "session", "camera", "ui", "database"])


if __name__ == "__main__":
    unittest.main()
