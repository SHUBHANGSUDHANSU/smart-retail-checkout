"""Tests for framework-independent operational health state."""

from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from smart_retail.application_state import ApplicationState
from smart_retail.health import (
    ComponentStatus,
    HealthComponent,
    HealthService,
)


class MutableClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def make_ready(service: HealthService) -> None:
    for component in (
        HealthComponent.CORE_SERVICES,
        HealthComponent.MODEL,
        HealthComponent.CAMERA,
        HealthComponent.VISION_PIPELINE,
        HealthComponent.DATABASE,
    ):
        service.mark_ready(component)
    service.set_application_state(ApplicationState.RUNNING)


class HealthServiceTests(unittest.TestCase):
    def test_intentionally_disabled_vision_components_are_readiness_acceptable(
        self,
    ) -> None:
        service = HealthService(
            database_enabled=True,
            disabled_components=(
                HealthComponent.MODEL,
                HealthComponent.CAMERA,
                HealthComponent.VISION_PIPELINE,
            ),
        )
        service.mark_ready(HealthComponent.CORE_SERVICES)
        service.mark_ready(HealthComponent.DATABASE)
        service.set_application_state(ApplicationState.RUNNING)

        snapshot = service.get_readiness()

        self.assertTrue(snapshot.ready)
        self.assertEqual(snapshot.components["model"], "disabled")
        self.assertEqual(snapshot.components["camera"], "disabled")
        self.assertEqual(snapshot.components["vision_pipeline"], "disabled")

    def test_core_and_database_cannot_use_disabled_components_argument(self) -> None:
        for component in (
            HealthComponent.CORE_SERVICES,
            HealthComponent.DATABASE,
        ):
            with self.subTest(component=component.value):
                with self.assertRaisesRegex(ValueError, "vision components"):
                    HealthService(
                        database_enabled=True,
                        disabled_components=(component,),
                    )

    def test_liveness_uses_monotonic_uptime_without_dependency_checks(self) -> None:
        clock = MutableClock()
        service = HealthService(database_enabled=True, clock=clock)
        service.mark_unavailable(HealthComponent.MODEL)
        clock.value = 112.5

        snapshot = service.get_liveness()

        self.assertEqual(snapshot.status, "ok")
        self.assertEqual(snapshot.uptime_seconds, 12.5)

    def test_all_required_components_produce_ready_snapshot(self) -> None:
        service = HealthService(database_enabled=True)
        make_ready(service)

        snapshot = service.get_readiness()

        self.assertTrue(snapshot.ready)
        self.assertEqual(snapshot.status, "ready")
        self.assertEqual(
            dict(snapshot.components),
            {
                "core_services": "ready",
                "model": "ready",
                "camera": "ready",
                "vision_pipeline": "ready",
                "database": "ready",
            },
        )

    def test_camera_unavailable_makes_application_not_ready(self) -> None:
        service = HealthService(database_enabled=True)
        make_ready(service)

        service.mark_unavailable(HealthComponent.CAMERA)

        snapshot = service.get_readiness()
        self.assertFalse(snapshot.ready)
        self.assertEqual(snapshot.status, "not_ready")
        self.assertEqual(snapshot.components["camera"], "unavailable")

    def test_model_unavailable_makes_application_not_ready(self) -> None:
        service = HealthService(database_enabled=True)
        make_ready(service)

        service.mark_unavailable(HealthComponent.MODEL)

        snapshot = service.get_readiness()
        self.assertFalse(snapshot.ready)
        self.assertEqual(snapshot.components["model"], "unavailable")

    def test_database_unavailable_makes_application_not_ready(self) -> None:
        service = HealthService(database_enabled=True)
        make_ready(service)

        service.mark_unavailable(HealthComponent.DATABASE)

        snapshot = service.get_readiness()
        self.assertFalse(snapshot.ready)
        self.assertEqual(snapshot.components["database"], "unavailable")

    def test_disabled_database_is_not_a_failed_dependency(self) -> None:
        service = HealthService(database_enabled=False)
        for component in (
            HealthComponent.CORE_SERVICES,
            HealthComponent.MODEL,
            HealthComponent.CAMERA,
            HealthComponent.VISION_PIPELINE,
        ):
            service.mark_ready(component)
        service.set_application_state(ApplicationState.RUNNING)

        snapshot = service.get_readiness()

        self.assertTrue(snapshot.ready)
        self.assertEqual(snapshot.components["database"], "disabled")

    def test_concurrent_transitions_and_snapshots_remain_internally_valid(self) -> None:
        service = HealthService(database_enabled=True)
        make_ready(service)
        start = threading.Barrier(5)

        def writer() -> None:
            start.wait(timeout=5)
            for _ in range(500):
                service.mark_unavailable(HealthComponent.CAMERA)
                service.mark_ready(HealthComponent.CAMERA)

        def reader() -> None:
            start.wait(timeout=5)
            for _ in range(500):
                snapshot = service.get_readiness()
                camera_ready = (
                    snapshot.components["camera"] == ComponentStatus.READY.value
                )
                self.assertEqual(snapshot.ready, camera_ready)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(writer)]
            futures.extend(executor.submit(reader) for _ in range(4))
            for future in futures:
                future.result(timeout=10)

        self.assertTrue(all(future.done() for future in futures))


if __name__ == "__main__":
    unittest.main()
