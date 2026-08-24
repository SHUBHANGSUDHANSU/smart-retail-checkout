"""Hardware-free tests for application persistence behavior."""

import io
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from smart_retail.app import SmartRetailApplication
from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutUpdate
from smart_retail.config import load_config
from smart_retail.domain.events import CartEventType, CheckoutEvent, CheckoutEventType
from smart_retail.domain.models import CheckoutSession
from smart_retail.health import HealthComponent, HealthService
from smart_retail.infrastructure.logging_config import EventFormatter
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.infrastructure.sqlite_repository import (
    PersistenceError,
    SQLiteCheckoutRepository,
)
from smart_retail.vision.pipeline import VisionResult


def initialized_health(database_enabled: bool) -> HealthService:
    health = HealthService(database_enabled=database_enabled)
    health.mark_ready(HealthComponent.CORE_SERVICES)
    health.mark_ready(HealthComponent.MODEL)
    if database_enabled:
        health.mark_ready(HealthComponent.DATABASE)
    return health


class ApplicationPersistenceTests(unittest.TestCase):
    def make_application(
        self,
        repository,
        session_id: int = 1,
    ) -> SmartRetailApplication:
        config = load_config({})
        logger_stream = io.StringIO()
        handler = logging.StreamHandler(logger_stream)
        handler.setFormatter(EventFormatter("%(levelname)s | %(message)s"))
        logger = logging.Logger("test.persistence.application", logging.DEBUG)
        logger.propagate = False
        logger.addHandler(handler)
        return SmartRetailApplication(
            config=config,
            logger=logger,
            camera=MagicMock(),
            vision=MagicMock(),
            event_engine=MagicMock(),
            cart=CartService(load_product_catalog(config.products_config_path)),
            ui=MagicMock(),
            health=initialized_health(config.database.enabled),
            persistence=repository,
            persistence_session_id=session_id,
        )

    def make_runtime_application(self, repository) -> SmartRetailApplication:
        config = load_config({})
        camera = MagicMock()
        camera.read.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        vision = MagicMock()
        vision.device = "cpu"
        vision.process.return_value = VisionResult((), 5.0)
        event_engine = MagicMock()
        event_engine.process_frame.return_value = CheckoutUpdate((), ())
        ui = MagicMock()
        ui.poll_key.return_value = ord("q")
        logger = logging.Logger("test.persistence.runtime", logging.DEBUG)
        logger.propagate = False
        logger.addHandler(logging.NullHandler())
        return SmartRetailApplication(
            config=config,
            logger=logger,
            camera=camera,
            vision=vision,
            event_engine=event_engine,
            cart=CartService(load_product_catalog(config.products_config_path)),
            ui=ui,
            health=initialized_health(config.database.enabled),
            persistence=repository,
        )

    def test_only_successful_business_mutations_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = load_config({})
            repository = SQLiteCheckoutRepository(
                Path(temporary_directory) / "history.db"
            )
            repository.initialize(load_product_catalog(config.products_config_path))
            session = repository.create_session(started_at=100.0)
            application = self.make_application(repository, session.session_id)
            enter = CheckoutEvent(
                CheckoutEventType.ENTER,
                track_id=7,
                product_class="bottle",
                timestamp=101.0,
            )

            application._apply_checkout_event(enter)
            application._apply_checkout_event(enter)
            application._apply_checkout_event(
                CheckoutEvent(
                    CheckoutEventType.EXIT,
                    track_id=7,
                    product_class="bottle",
                    timestamp=102.0,
                )
            )
            application._reset_checkout()

            events = repository.get_session_events(session.session_id)
            self.assertEqual(
                [event.event_type for event in events],
                [CartEventType.ADD, CartEventType.REMOVE, CartEventType.RESET],
            )

    def test_persistence_failure_does_not_undo_in_memory_cart(self) -> None:
        repository = MagicMock()
        repository.record_cart_event.side_effect = PersistenceError("disk full")
        application = self.make_application(repository)

        application._apply_checkout_event(
            CheckoutEvent(
                CheckoutEventType.ENTER,
                track_id=7,
                product_class="bottle",
                timestamp=101.0,
            )
        )

        self.assertTrue(application.cart.contains_track(7))
        self.assertEqual(application.cart.get_total(), 40)
        self.assertIsNone(application.persistence)
        self.assertIsNone(application.persistence_session_id)
        self.assertEqual(
            application.get_metrics_snapshot().persistence_errors_total,
            1,
        )

    def test_application_run_opens_and_closes_history_session(self) -> None:
        repository = MagicMock()
        repository.create_session.return_value = CheckoutSession(9, 100.0, None, None)
        application = self.make_runtime_application(repository)

        exit_code = application.run()

        self.assertEqual(exit_code, 0)
        repository.create_session.assert_called_once_with()
        repository.close_session.assert_called_once_with(9, final_total=0)
        repository.record_cart_event.assert_not_called()

    def test_session_creation_failure_does_not_stop_webcam_loop(self) -> None:
        repository = MagicMock()
        repository.create_session.side_effect = PersistenceError("database locked")
        application = self.make_runtime_application(repository)

        exit_code = application.run()

        self.assertEqual(exit_code, 0)
        application.camera.open.assert_called_once()
        application.camera.release.assert_called_once()
        self.assertIsNone(application.persistence)
        repository.close_session.assert_not_called()
        self.assertEqual(
            application.get_metrics_snapshot().persistence_errors_total,
            1,
        )


if __name__ == "__main__":
    unittest.main()
