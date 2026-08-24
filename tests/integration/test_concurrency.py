"""Deterministic concurrency tests for shared checkout state."""

from __future__ import annotations

import logging
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from smart_retail.app import SmartRetailApplication
from smart_retail.application_state import ApplicationState
from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutEventEngine
from smart_retail.checkout.zone import CheckoutZone
from smart_retail.config import load_config
from smart_retail.domain.events import CartEventType
from smart_retail.domain.models import CartSnapshot, TrackedObject
from smart_retail.health import HealthComponent, HealthService
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.infrastructure.sqlite_repository import (
    PersistenceError,
    SQLiteCheckoutRepository,
)
from smart_retail.vision.pipeline import VisionResult


def initialized_health(database_enabled: bool, running: bool = False) -> HealthService:
    health = HealthService(database_enabled=database_enabled)
    health.mark_ready(HealthComponent.CORE_SERVICES)
    health.mark_ready(HealthComponent.MODEL)
    if database_enabled:
        health.mark_ready(HealthComponent.DATABASE)
    if running:
        health.mark_ready(HealthComponent.CAMERA)
        health.mark_ready(HealthComponent.VISION_PIPELINE)
        health.set_application_state(ApplicationState.RUNNING)
    return health


def observation(track_id: int, center_x: int) -> TrackedObject:
    return TrackedObject(
        track_id=track_id,
        class_name="bottle",
        confidence=0.95,
        bbox=(center_x - 10, 240, center_x + 10, 260),
    )


def assert_snapshot_consistent(
    test_case: unittest.TestCase,
    snapshot: CartSnapshot,
) -> None:
    expected_quantity = sum(item.quantity for item in snapshot.items)
    expected_total = sum(item.quantity * item.unit_price for item in snapshot.items)
    test_case.assertEqual(snapshot.total_quantity, expected_quantity)
    test_case.assertEqual(snapshot.total, expected_total)


class CartConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        config = load_config({"SMART_RETAIL_API_ENABLED": "false"})
        products = load_product_catalog(config.products_config_path)
        self.cart = CartService(products)

    def test_simultaneous_reads_and_writes_keep_snapshots_consistent(self) -> None:
        start = threading.Barrier(6)
        failures: list[BaseException] = []

        def writer(worker_id: int) -> None:
            try:
                start.wait(timeout=5)
                first_track = worker_id * 1_000
                for offset in range(500):
                    track_id = first_track + offset
                    self.cart.add_item(track_id, "bottle")
                    if offset % 2 == 0:
                        self.cart.remove_item(track_id)
            except BaseException as error:
                failures.append(error)

        def reader() -> None:
            try:
                start.wait(timeout=5)
                for _ in range(750):
                    assert_snapshot_consistent(self, self.cart.get_snapshot())
            except BaseException as error:
                failures.append(error)

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(writer, worker_id) for worker_id in range(3)]
            futures.extend(executor.submit(reader) for _ in range(3))
            for future in futures:
                future.result(timeout=10)

        self.assertEqual(failures, [])
        final_snapshot = self.cart.get_snapshot()
        assert_snapshot_consistent(self, final_snapshot)
        self.assertEqual(final_snapshot.total_quantity, 750)
        self.assertEqual(final_snapshot.total, 30_000)

    def test_repeated_concurrent_reads_return_independent_snapshots(self) -> None:
        for track_id in range(100):
            self.cart.add_item(track_id, "apple")

        start = threading.Barrier(8)

        def reader() -> tuple[CartSnapshot, ...]:
            start.wait(timeout=5)
            return tuple(self.cart.get_snapshot() for _ in range(200))

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = [executor.submit(reader) for _ in range(8)]
            snapshots = [
                snapshot for future in results for snapshot in future.result(timeout=10)
            ]

        self.cart.clear()
        for snapshot in snapshots:
            assert_snapshot_consistent(self, snapshot)
            self.assertEqual(snapshot.total_quantity, 100)
            self.assertEqual(snapshot.total, 4_500)


class ApplicationConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.config = load_config(
            {
                "SMART_RETAIL_API_ENABLED": "false",
                "SMART_RETAIL_DATABASE_PATH": str(
                    Path(self.temporary_directory.name) / "concurrency.db"
                ),
            }
        )
        products = load_product_catalog(self.config.products_config_path)
        self.repository = SQLiteCheckoutRepository(self.config.database.path)
        self.repository.initialize(products)
        session = self.repository.create_session(started_at=100.0)
        logger = logging.Logger("test.concurrency")
        logger.propagate = False
        logger.addHandler(logging.NullHandler())
        self.application = SmartRetailApplication(
            config=self.config,
            logger=logger,
            camera=MagicMock(),
            vision=MagicMock(),
            event_engine=CheckoutEventEngine(
                CheckoutZone(0.70, 0.05, 0.98, 0.95),
                confirmation_frames=1,
                expiry_grace_frames=90,
            ),
            cart=CartService(products),
            ui=MagicMock(),
            persistence=self.repository,
            persistence_session_id=session.session_id,
            health=initialized_health(
                self.config.database.enabled,
                running=True,
            ),
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_reset_racing_with_enter_has_one_deterministic_empty_result(self) -> None:
        self.application.process_checkout_frame(
            (observation(7, 500),),
            frame_width=1_000,
            frame_height=500,
            frame_number=0,
        )
        start = threading.Barrier(2)

        def enter() -> None:
            start.wait(timeout=5)
            self.application.process_checkout_frame(
                (observation(7, 800),),
                frame_width=1_000,
                frame_height=500,
                frame_number=1,
            )

        def reset() -> None:
            start.wait(timeout=5)
            self.application.reset_checkout(source="api")

        with ThreadPoolExecutor(max_workers=2) as executor:
            enter_future = executor.submit(enter)
            reset_future = executor.submit(reset)
            enter_future.result(timeout=5)
            reset_future.result(timeout=5)

        snapshot = self.application.get_cart_snapshot()
        self.assertEqual(snapshot.items, ())
        self.assertEqual(snapshot.total, 0)
        events = self.repository.get_session_events(
            self.application.persistence_session_id
        )
        self.assertEqual(events[-1].event_type, CartEventType.RESET)

    def test_sqlite_reads_are_safe_during_vision_event_writes(self) -> None:
        self.application.process_checkout_frame(
            (observation(7, 500),),
            frame_width=1_000,
            frame_height=500,
            frame_number=0,
        )
        start = threading.Barrier(5)
        failures: list[BaseException] = []

        def writer() -> None:
            try:
                start.wait(timeout=5)
                for frame_number in range(1, 81):
                    center_x = 800 if frame_number % 2 else 500
                    self.application.process_checkout_frame(
                        (observation(7, center_x),),
                        frame_width=1_000,
                        frame_height=500,
                        frame_number=frame_number,
                    )
            except BaseException as error:
                failures.append(error)

        def reader() -> None:
            try:
                start.wait(timeout=5)
                for _ in range(100):
                    events = self.application.get_recent_cart_events(limit=200)
                    self.assertTrue(all(event.session_id > 0 for event in events))
            except BaseException as error:
                failures.append(error)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(writer)]
            futures.extend(executor.submit(reader) for _ in range(4))
            for future in futures:
                future.result(timeout=15)

        self.assertEqual(failures, [])
        self.assertEqual(len(self.repository.get_session_events(1)), 80)

    def test_stale_successful_read_cannot_override_database_disable(self) -> None:
        read_started = threading.Event()
        release_read = threading.Event()

        def delayed_read(limit: int):
            read_started.set()
            self.assertTrue(release_read.wait(timeout=5))
            return []

        self.repository.get_recent_events = delayed_read
        with ThreadPoolExecutor(max_workers=1) as executor:
            read_future = executor.submit(
                self.application.get_recent_cart_events,
                10,
            )
            self.assertTrue(read_started.wait(timeout=2))
            self.application._disable_persistence(
                "test_failure",
                PersistenceError("database disabled"),
            )
            release_read.set()
            self.assertEqual(read_future.result(timeout=5), [])

        snapshot = self.application.get_readiness_snapshot()
        self.assertIsNone(self.application.persistence)
        self.assertEqual(snapshot.components["database"], "unavailable")
        self.assertFalse(snapshot.ready)

    def test_database_is_published_unavailable_before_repository_is_cleared(
        self,
    ) -> None:
        publication_started = threading.Event()
        release_publication = threading.Event()
        original_mark_unavailable = self.application.health.mark_unavailable

        def delayed_mark_unavailable(component: HealthComponent) -> None:
            publication_started.set()
            self.assertTrue(release_publication.wait(timeout=5))
            original_mark_unavailable(component)

        self.application.health.mark_unavailable = delayed_mark_unavailable
        with ThreadPoolExecutor(max_workers=1) as executor:
            disable_future = executor.submit(
                self.application._disable_persistence,
                "test_failure",
                PersistenceError("database disabled"),
            )
            self.assertTrue(publication_started.wait(timeout=2))
            self.assertIs(self.application.persistence, self.repository)
            release_publication.set()
            disable_future.result(timeout=5)

        snapshot = self.application.get_readiness_snapshot()
        self.assertIsNone(self.application.persistence)
        self.assertEqual(snapshot.components["database"], "unavailable")


class LockScopeTests(unittest.TestCase):
    def test_slow_opencv_render_does_not_block_cart_reads(self) -> None:
        config = load_config(
            {
                "SMART_RETAIL_API_ENABLED": "false",
                "SMART_RETAIL_DATABASE_ENABLED": "false",
            }
        )
        products = load_product_catalog(config.products_config_path)
        camera = MagicMock()
        camera.read.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        vision = MagicMock()
        vision.device = "cpu"
        vision.process.return_value = VisionResult((), 1.0)
        render_started = threading.Event()
        release_render = threading.Event()
        ui = MagicMock()

        def slow_render(*args: object, **kwargs: object) -> None:
            render_started.set()
            self.assertTrue(release_render.wait(timeout=5))

        ui.render.side_effect = slow_render
        ui.poll_key.return_value = ord("q")
        application = SmartRetailApplication(
            config=config,
            logger=logging.getLogger("test.lock-scope"),
            camera=camera,
            vision=vision,
            event_engine=CheckoutEventEngine(
                CheckoutZone(0.70, 0.05, 0.98, 0.95),
                confirmation_frames=1,
                expiry_grace_frames=90,
            ),
            cart=CartService(products),
            ui=ui,
            health=initialized_health(config.database.enabled),
        )
        run_result: list[int] = []
        run_thread = threading.Thread(
            target=lambda: run_result.append(application.run())
        )
        run_thread.start()
        self.assertTrue(render_started.wait(timeout=2))

        with ThreadPoolExecutor(max_workers=1) as executor:
            snapshot_future = executor.submit(application.get_cart_snapshot)
            try:
                snapshot = snapshot_future.result(timeout=0.5)
            finally:
                release_render.set()

        run_thread.join(timeout=5)
        self.assertFalse(run_thread.is_alive())
        self.assertEqual(run_result, [0])
        self.assertEqual(snapshot.total, 0)


if __name__ == "__main__":
    unittest.main()
