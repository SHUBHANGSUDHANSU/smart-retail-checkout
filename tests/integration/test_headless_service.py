"""Vision-free integration tests for the headless FastAPI/SQLite runtime."""

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from smart_retail.api.service import HeadlessAPIRuntime, create_service_app
from smart_retail.application_state import ApplicationState
from smart_retail.config import load_config
from smart_retail.domain.events import CartEventType
from smart_retail.health import HealthComponent
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.infrastructure.sqlite_repository import (
    PersistenceError,
    SQLiteCheckoutRepository,
)


def quiet_logger() -> logging.Logger:
    logger = logging.Logger("test.api.service", logging.DEBUG)
    logger.propagate = False
    logger.addHandler(logging.NullHandler())
    return logger


class HeadlessAPIServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "service.db"
        self.config = load_config(
            {
                "SMART_RETAIL_API_ENABLED": "true",
                "SMART_RETAIL_DATABASE_PATH": str(self.database_path),
            }
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_lifespan_exposes_ready_service_state_and_finalizes_session(self) -> None:
        application = create_service_app(self.config, quiet_logger())

        with TestClient(application) as client:
            health = client.get("/health")
            ready = client.get("/ready")
            cart = client.get("/api/v1/cart")
            reset = client.post("/api/v1/cart/reset")
            events = client.get("/api/v1/events?limit=1")
            sessions = client.get("/api/v1/sessions?limit=1")
            metrics = client.get("/api/v1/metrics")
            openapi = client.get("/openapi.json")
            session_id = sessions.json()["sessions"][0]["id"]

            self.assertEqual(health.status_code, 200)
            self.assertEqual(ready.status_code, 200)
            self.assertEqual(
                ready.json()["components"],
                {
                    "core_services": "ready",
                    "model": "disabled",
                    "camera": "disabled",
                    "vision_pipeline": "disabled",
                    "database": "ready",
                },
            )
            self.assertEqual(
                cart.json(), {"items": [], "total_quantity": 0, "total": 0}
            )
            self.assertEqual(reset.status_code, 200)
            self.assertEqual(reset.json()["removed_track_count"], 0)
            self.assertEqual(events.json()["events"][0]["event_type"], "RESET")
            self.assertEqual(metrics.json()["cart_resets_total"], 1)
            self.assertIn("/api/v1/metrics", openapi.json()["paths"])

        repository = SQLiteCheckoutRepository(self.database_path)
        repository.initialize(load_product_catalog(self.config.products_config_path))
        closed_session = repository.get_session(session_id)
        self.assertIsNotNone(closed_session)
        self.assertIsNotNone(closed_session.ended_at)
        self.assertEqual(closed_session.final_total, 0)
        repository.close()

    def test_runtime_stop_is_idempotent(self) -> None:
        products = load_product_catalog(self.config.products_config_path)
        real_repository = SQLiteCheckoutRepository(self.database_path)
        repository = MagicMock(wraps=real_repository)
        runtime = HeadlessAPIRuntime(
            config=self.config,
            logger=quiet_logger(),
            products=products,
            repository=repository,
        )

        runtime.start()
        runtime.stop()
        runtime.stop()

        repository.close_session.assert_called_once()
        repository.close.assert_called_once_with()

    def test_failed_session_close_retains_state_for_shutdown_retry(self) -> None:
        products = load_product_catalog(self.config.products_config_path)
        real_repository = SQLiteCheckoutRepository(self.database_path)
        repository = MagicMock(wraps=real_repository)
        real_close_session = real_repository.close_session
        close_attempts = 0

        def close_session_with_one_failure(*args, **kwargs):
            nonlocal close_attempts
            close_attempts += 1
            if close_attempts == 1:
                raise PersistenceError("temporary close failure")
            return real_close_session(*args, **kwargs)

        repository.close_session.side_effect = close_session_with_one_failure
        runtime = HeadlessAPIRuntime(
            config=self.config,
            logger=quiet_logger(),
            products=products,
            repository=repository,
        )
        runtime.start()

        with self.assertRaises(PersistenceError):
            runtime.stop()

        self.assertEqual(
            runtime.get_readiness_snapshot().application_state,
            ApplicationState.ERROR,
        )
        repository.close.assert_not_called()

        runtime.stop()

        self.assertEqual(repository.close_session.call_count, 2)
        repository.close.assert_called_once_with()
        self.assertEqual(
            runtime.get_readiness_snapshot().application_state,
            ApplicationState.STOPPED,
        )

    def test_reset_uses_real_cart_service_and_persists_reset_event(self) -> None:
        application = create_service_app(self.config, quiet_logger())
        with TestClient(application):
            runtime = application.state.runtime

            result = runtime.reset_checkout(source="api")
            persisted = runtime.get_recent_cart_events(limit=1)

            self.assertEqual(result.cart.total, 0)
            self.assertEqual(result.removed_track_count, 0)
            self.assertEqual(persisted[0].event_type, CartEventType.RESET)
            self.assertEqual(
                runtime.get_metrics_snapshot().cart_resets_total,
                1,
            )

    def test_history_read_failures_update_readiness_and_metrics(self) -> None:
        products = load_product_catalog(self.config.products_config_path)
        repository = MagicMock(wraps=SQLiteCheckoutRepository(self.database_path))
        runtime = HeadlessAPIRuntime(
            config=self.config,
            logger=quiet_logger(),
            products=products,
            repository=repository,
        )
        runtime.start()
        failing_calls = (
            (repository.get_recent_events, lambda: runtime.get_recent_cart_events(1)),
            (
                repository.get_recent_sessions,
                lambda: runtime.get_recent_checkout_sessions(1),
            ),
            (repository.get_session, lambda: runtime.get_checkout_session_history(1)),
        )

        try:
            for failure_number, (repository_method, runtime_call) in enumerate(
                failing_calls,
                start=1,
            ):
                with self.subTest(repository_method=repository_method._mock_name):
                    runtime.health.mark_ready(HealthComponent.DATABASE)
                    repository_method.side_effect = PersistenceError("read failed")

                    with self.assertRaises(PersistenceError):
                        runtime_call()

                    readiness = runtime.get_readiness_snapshot()
                    self.assertEqual(
                        readiness.components["database"],
                        "unavailable",
                    )
                    self.assertEqual(
                        runtime.get_metrics_snapshot().persistence_errors_total,
                        failure_number,
                    )
                    repository_method.side_effect = None
        finally:
            runtime.stop()
