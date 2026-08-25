"""FastAPI tests over shared in-memory state and temporary SQLite history."""

import logging
import tempfile
import unittest
from pathlib import Path
from typing import Any, get_type_hints
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from smart_retail.api.dependencies import get_runtime
from smart_retail.api.factory import create_api_app
from smart_retail.app import SmartRetailApplication
from smart_retail.application_state import ApplicationState
from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutEventEngine
from smart_retail.checkout.zone import CheckoutZone
from smart_retail.config import load_config
from smart_retail.domain.events import CartEventType, CheckoutEventType
from smart_retail.domain.models import TrackedObject
from smart_retail.health import HealthComponent, HealthService
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.infrastructure.sqlite_repository import (
    PersistenceError,
    SQLiteCheckoutRepository,
)


def ready_health_service(database_enabled: bool = True) -> HealthService:
    service = HealthService(database_enabled=database_enabled)
    for component in (
        HealthComponent.CORE_SERVICES,
        HealthComponent.MODEL,
        HealthComponent.CAMERA,
        HealthComponent.VISION_PIPELINE,
    ):
        service.mark_ready(component)
    if database_enabled:
        service.mark_ready(HealthComponent.DATABASE)
    service.set_application_state(ApplicationState.RUNNING)
    return service


class SmartRetailAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.config = load_config(
            {
                "SMART_RETAIL_API_ENABLED": "false",
                "SMART_RETAIL_DATABASE_PATH": str(
                    Path(self.temporary_directory.name) / "api.db"
                ),
            }
        )
        products = load_product_catalog(self.config.products_config_path)
        self.repository = SQLiteCheckoutRepository(self.config.database.path)
        self.repository.initialize(products)
        self.session = self.repository.create_session(started_at=100.0)
        self.repository.record_cart_event(
            self.session.session_id,
            CartEventType.ADD,
            timestamp=101.0,
            track_id=7,
            product_id="bottle",
            unit_price=40,
        )
        self.repository.record_cart_event(
            self.session.session_id,
            CartEventType.ADD,
            timestamp=102.0,
            track_id=12,
            product_id="apple",
            unit_price=45,
        )

        logger = logging.Logger("test.api", logging.DEBUG)
        logger.propagate = False
        logger.addHandler(logging.NullHandler())
        self.event_engine = CheckoutEventEngine(
            CheckoutZone(0.70, 0.05, 0.98, 0.95),
            confirmation_frames=1,
            expiry_grace_frames=90,
        )
        self.cart = CartService(products)
        self.cart.add_item(7, "bottle")
        self.cart.add_item(12, "apple")
        self.cart.add_item(19, "bottle")
        self.runtime = SmartRetailApplication(
            config=self.config,
            logger=logger,
            camera=MagicMock(),
            vision=MagicMock(),
            event_engine=self.event_engine,
            cart=self.cart,
            ui=MagicMock(),
            persistence=self.repository,
            persistence_session_id=self.session.session_id,
            health=ready_health_service(),
        )
        self.client = TestClient(
            create_api_app(self.runtime),
            raise_server_exceptions=False,
        )

    def tearDown(self) -> None:
        self.client.close()
        self.temporary_directory.cleanup()

    def test_health_reports_liveness_without_dependency_probes(self) -> None:
        self.repository.is_ready = MagicMock(
            side_effect=AssertionError("health routes must not probe SQLite")
        )
        health = self.client.get("/health")
        ready = self.client.get("/ready")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        self.repository.is_ready.assert_not_called()
        self.assertEqual(health.json()["status"], "ok")
        self.assertGreaterEqual(health.json()["uptime_seconds"], 0)

        self.runtime.health.mark_unavailable(HealthComponent.MODEL)
        still_live = self.client.get("/health")
        self.assertEqual(still_live.status_code, 200)
        self.assertEqual(still_live.json()["status"], "ok")

    def test_route_dependency_exposes_a_runtime_contract(self) -> None:
        runtime_type = get_type_hints(get_runtime)["return"]

        self.assertIsNot(runtime_type, Any)
        self.assertIsInstance(self.runtime, runtime_type)

    def test_readiness_reports_cached_component_state(self) -> None:
        ready = self.client.get("/ready")

        self.assertEqual(ready.status_code, 200)
        self.assertEqual(
            ready.json(),
            {
                "status": "ready",
                "application_state": "running",
                "components": {
                    "core_services": "ready",
                    "model": "ready",
                    "camera": "ready",
                    "vision_pipeline": "ready",
                    "database": "ready",
                },
            },
        )

    def test_readiness_fails_for_each_unavailable_critical_component(self) -> None:
        for component in (
            HealthComponent.CAMERA,
            HealthComponent.MODEL,
            HealthComponent.DATABASE,
        ):
            with self.subTest(component=component.value):
                self.runtime.health = ready_health_service()
                self.runtime.health.mark_unavailable(component)

                not_ready = self.client.get("/ready")

                self.assertEqual(not_ready.status_code, 503)
                self.assertEqual(not_ready.json()["status"], "not_ready")
                self.assertEqual(
                    not_ready.json()["components"][component.value],
                    "unavailable",
                )

    def test_cart_returns_aggregated_shared_state(self) -> None:
        response = self.client.get("/api/v1/cart")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_quantity"], 3)
        self.assertEqual(payload["total"], 125)
        self.assertEqual(
            payload["items"][0],
            {
                "product_id": "bottle",
                "product_name": "Water Bottle",
                "quantity": 2,
                "unit_price": 40,
                "subtotal": 80,
            },
        )

    def test_metrics_returns_one_shared_in_memory_snapshot(self) -> None:
        self.runtime.metrics.record_frame(3, 2, 12.0, 18.0, 27.5)
        self.runtime.metrics.record_checkout_event(CheckoutEventType.ENTER)
        self.runtime.metrics.record_cart_addition(self.runtime.get_cart_snapshot())

        response = self.client.get("/api/v1/metrics")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["frames_processed_total"], 1)
        self.assertEqual(payload["detections_total"], 3)
        self.assertEqual(payload["active_tracks"], 2)
        self.assertEqual(payload["inference_latency_ms"], 12.0)
        self.assertEqual(payload["frame_processing_latency_ms"], 18.0)
        self.assertEqual(payload["current_fps"], 27.5)
        self.assertEqual(payload["checkout_enter_events_total"], 1)
        self.assertEqual(payload["cart_additions_total"], 1)
        self.assertEqual(payload["current_cart_items"], 3)
        self.assertEqual(payload["current_cart_total"], 125)
        self.assertGreaterEqual(payload["uptime_seconds"], 0.0)

    def test_api_reset_uses_shared_cart_and_event_engine(self) -> None:
        self.event_engine.process_frame(
            (TrackedObject(7, "bottle", 0.95, (490, 240, 510, 260)),),
            frame_width=1_000,
            frame_height=500,
            frame_number=0,
        )
        self.assertNotEqual(dict(self.event_engine.get_snapshot().track_states), {})

        response = self.client.post("/api/v1/cart/reset")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_track_count"], 3)
        self.assertEqual(response.json()["cart"]["total"], 0)
        self.assertEqual(self.cart.get_total(), 0)
        self.assertEqual(dict(self.event_engine.get_snapshot().track_states), {})
        self.assertEqual(
            self.repository.get_recent_events(limit=1)[0].event_type,
            CartEventType.RESET,
        )

    def test_api_reset_requires_running_application(self) -> None:
        self.runtime.health.set_application_state(ApplicationState.STOPPING)

        response = self.client.post("/api/v1/cart/reset")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "application_not_ready")
        self.assertEqual(self.cart.get_total(), 125)

    def test_recent_events_return_persisted_history_for_explicit_limit(self) -> None:
        response = self.client.get("/api/v1/events?limit=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "events": [
                    {
                        "id": 2,
                        "session_id": self.session.session_id,
                        "timestamp": "1970-01-01T00:01:42Z",
                        "track_id": 12,
                        "product_id": "apple",
                        "event_type": "ADD",
                        "unit_price": 45,
                    },
                    {
                        "id": 1,
                        "session_id": self.session.session_id,
                        "timestamp": "1970-01-01T00:01:41Z",
                        "track_id": 7,
                        "product_id": "bottle",
                        "event_type": "ADD",
                        "unit_price": 40,
                    },
                ],
                "limit": 10,
            },
        )

    def test_sessions_and_session_detail_use_persisted_history(self) -> None:
        sessions = self.client.get("/api/v1/sessions?limit=10")
        detail = self.client.get(f"/api/v1/sessions/{self.session.session_id}")

        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(
            sessions.json(),
            {
                "sessions": [
                    {
                        "id": self.session.session_id,
                        "started_at": "1970-01-01T00:01:40Z",
                        "ended_at": None,
                        "final_total": None,
                    }
                ],
                "limit": 10,
            },
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], self.session.session_id)
        self.assertEqual(len(detail.json()["events"]), 2)
        self.assertEqual(detail.json()["events"][0]["event_type"], "ADD")

    def test_history_limits_reject_zero_above_maximum_and_nonintegers(self) -> None:
        invalid_paths = (
            "/api/v1/events?limit=0",
            "/api/v1/events?limit=201",
            "/api/v1/events?limit=ten",
            "/api/v1/sessions?limit=0",
            "/api/v1/sessions?limit=101",
            "/api/v1/sessions?limit=ten",
        )

        for path in invalid_paths:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json(),
                    {
                        "code": "validation_error",
                        "message": "Request validation failed.",
                    },
                )

    def test_missing_session_returns_safe_404(self) -> None:
        response = self.client.get("/api/v1/sessions/999999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "code": "session_not_found",
                "message": "Checkout session 999999 was not found.",
            },
        )
        self.assertNotIn("Traceback", response.text)

    def test_unavailable_persistence_returns_safe_503(self) -> None:
        self.runtime.persistence = None

        response = self.client.get("/api/v1/events")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "persistence_unavailable")
        self.assertNotIn("SQLite checkout history", response.text)

    def test_database_read_failure_updates_cached_readiness(self) -> None:
        self.repository.get_recent_events = MagicMock(
            side_effect=PersistenceError("database unavailable")
        )

        events = self.client.get("/api/v1/events")
        ready = self.client.get("/ready")

        self.assertEqual(events.status_code, 503)
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(
            ready.json()["components"]["database"],
            "unavailable",
        )

    def test_history_request_preserves_intentionally_disabled_database(self) -> None:
        self.runtime.config = load_config(
            {
                "SMART_RETAIL_API_ENABLED": "false",
                "SMART_RETAIL_DATABASE_ENABLED": "false",
            }
        )
        self.runtime.persistence = None
        self.runtime.health = ready_health_service(database_enabled=False)

        events = self.client.get("/api/v1/events")
        ready = self.client.get("/ready")

        self.assertEqual(events.status_code, 503)
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["components"]["database"], "disabled")

    def test_openapi_and_swagger_are_available(self) -> None:
        schema_response = self.client.get("/openapi.json")
        docs_response = self.client.get("/docs")

        self.assertEqual(schema_response.status_code, 200)
        self.assertIn("/api/v1/cart", schema_response.json()["paths"])
        self.assertIn("/api/v1/metrics", schema_response.json()["paths"])
        self.assertIn("/ready", schema_response.json()["paths"])
        self.assertEqual(docs_response.status_code, 200)

    def test_openapi_describes_safe_error_responses(self) -> None:
        schema = self.client.get("/openapi.json").json()
        error_schema = {"$ref": "#/components/schemas/ErrorResponse"}

        def response_schema(path: str, method: str, status_code: int):
            return schema["paths"][path][method]["responses"][str(status_code)][
                "content"
            ]["application/json"]["schema"]

        self.assertEqual(
            response_schema("/api/v1/events", "get", 422),
            error_schema,
        )
        self.assertEqual(
            response_schema("/api/v1/events", "get", 503),
            error_schema,
        )
        self.assertEqual(
            response_schema("/api/v1/sessions/{session_id}", "get", 404),
            error_schema,
        )
        self.assertEqual(
            response_schema("/api/v1/cart/reset", "post", 503),
            error_schema,
        )
        self.assertEqual(
            response_schema("/api/v1/cart", "get", 500),
            error_schema,
        )

    def test_api_responses_disable_sniffing_and_shared_caching(self) -> None:
        response = self.client.get("/api/v1/cart")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_api_does_not_allow_cross_origin_requests_by_default(self) -> None:
        response = self.client.get(
            "/api/v1/cart",
            headers={"Origin": "https://example.invalid"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_configured_frontend_origin_receives_cors_header(self) -> None:
        client = TestClient(
            create_api_app(
                self.runtime,
                allowed_origins=("http://localhost:5173",),
            )
        )
        try:
            response = client.get(
                "/health",
                headers={"Origin": "http://localhost:5173"},
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )

    def test_unlisted_origin_receives_no_cors_permission(self) -> None:
        client = TestClient(
            create_api_app(
                self.runtime,
                allowed_origins=("http://localhost:5173",),
            )
        )
        try:
            response = client.get(
                "/health",
                headers={"Origin": "https://example.invalid"},
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_configured_frontend_origin_can_preflight_health_get(self) -> None:
        client = TestClient(
            create_api_app(
                self.runtime,
                allowed_origins=("http://localhost:5173",),
            )
        )
        try:
            response = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("GET", response.headers["access-control-allow-methods"])

    def test_configured_frontend_origin_can_preflight_cart_reset_post(self) -> None:
        client = TestClient(
            create_api_app(
                self.runtime,
                allowed_origins=("http://localhost:5173",),
            )
        )
        try:
            response = client.options(
                "/api/v1/cart/reset",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                },
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("POST", response.headers["access-control-allow-methods"])
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )

    def test_cors_does_not_block_simple_post_to_existing_route(self) -> None:
        client = TestClient(
            create_api_app(
                self.runtime,
                allowed_origins=("http://localhost:5173",),
            )
        )
        try:
            response = client.post(
                "/api/v1/cart/reset",
                headers={"Origin": "http://localhost:5173"},
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_track_count"], 3)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )
        self.assertEqual(self.cart.get_total(), 0)

    def test_unlisted_origin_can_trigger_reset_but_cannot_read_response(self) -> None:
        client = TestClient(
            create_api_app(
                self.runtime,
                allowed_origins=("http://localhost:5173",),
            )
        )
        try:
            response = client.post(
                "/api/v1/cart/reset",
                headers={"Origin": "https://example.invalid"},
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_track_count"], 3)
        self.assertNotIn("access-control-allow-origin", response.headers)
        self.assertEqual(self.cart.get_total(), 0)

    def test_cart_reset_rejects_the_get_method(self) -> None:
        response = self.client.get("/api/v1/cart/reset")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.cart.get_total(), 125)

    def test_unexpected_route_failure_returns_safe_500(self) -> None:
        failing_runtime = MagicMock()
        failing_runtime.get_cart_snapshot.side_effect = RuntimeError(
            "sensitive internal detail"
        )
        client = TestClient(
            create_api_app(failing_runtime),
            raise_server_exceptions=False,
        )
        try:
            response = client.get("/api/v1/cart")
        finally:
            client.close()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["code"], "internal_error")
        self.assertNotIn("sensitive internal detail", response.text)


if __name__ == "__main__":
    unittest.main()
