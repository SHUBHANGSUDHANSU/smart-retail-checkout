"""Deterministic tests for bounded, thread-safe application metrics."""

import dataclasses
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from smart_retail.config import ConfigurationError, load_config
from smart_retail.domain.events import CheckoutEventType
from smart_retail.domain.models import CartItem, CartSnapshot
from smart_retail.metrics import MetricsService


def cart_snapshot(quantity: int, total: int) -> CartSnapshot:
    items = (
        (CartItem("bottle", "Water Bottle", total // quantity, quantity),)
        if quantity
        else ()
    )
    return CartSnapshot(items=items, total=total)


class MetricsServiceTests(unittest.TestCase):
    def test_counters_and_gauges_update_without_cross_talk(self) -> None:
        metrics = MetricsService(rolling_window_size=3, clock=lambda: 10.0)

        metrics.record_frame(
            detection_count=3,
            active_tracks=2,
            inference_latency_ms=12.0,
            frame_processing_latency_ms=18.0,
            current_fps=27.5,
        )
        metrics.record_dropped_frame()
        metrics.record_checkout_event(CheckoutEventType.ENTER)
        metrics.record_checkout_event(CheckoutEventType.EXIT)
        metrics.record_cart_addition(cart_snapshot(2, 80))
        metrics.record_cart_removal(cart_snapshot(1, 40))
        metrics.record_cart_reset(cart_snapshot(0, 0))
        metrics.record_camera_error()
        metrics.record_persistence_error()

        snapshot = metrics.get_snapshot()
        self.assertEqual(snapshot.frames_processed_total, 1)
        self.assertEqual(snapshot.dropped_frames_total, 1)
        self.assertEqual(snapshot.detections_total, 3)
        self.assertEqual(snapshot.active_tracks, 2)
        self.assertEqual(snapshot.current_fps, 27.5)
        self.assertEqual(snapshot.checkout_enter_events_total, 1)
        self.assertEqual(snapshot.checkout_exit_events_total, 1)
        self.assertEqual(snapshot.cart_additions_total, 1)
        self.assertEqual(snapshot.cart_removals_total, 1)
        self.assertEqual(snapshot.cart_resets_total, 1)
        self.assertEqual(snapshot.current_cart_items, 0)
        self.assertEqual(snapshot.current_cart_total, 0)
        self.assertEqual(snapshot.camera_errors_total, 1)
        self.assertEqual(snapshot.persistence_errors_total, 1)

    def test_rolling_latency_averages_evict_old_samples(self) -> None:
        metrics = MetricsService(rolling_window_size=2)
        for inference, processing in ((10.0, 20.0), (20.0, 30.0), (40.0, 50.0)):
            metrics.record_frame(
                detection_count=0,
                active_tracks=0,
                inference_latency_ms=inference,
                frame_processing_latency_ms=processing,
                current_fps=25.0,
            )

        snapshot = metrics.get_snapshot()
        self.assertEqual(snapshot.inference_latency_ms, 30.0)
        self.assertEqual(snapshot.frame_processing_latency_ms, 40.0)

    def test_uptime_uses_injected_monotonic_clock_and_snapshot_is_frozen(self) -> None:
        times = iter((100.0, 104.25))
        metrics = MetricsService(clock=lambda: next(times))

        snapshot = metrics.get_snapshot()

        self.assertEqual(snapshot.uptime_seconds, 4.25)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.current_fps = 1.0

    def test_invalid_measurements_are_rejected(self) -> None:
        metrics = MetricsService()
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            metrics.record_frame(-1, 0, 1.0, 1.0, 1.0)
        for detection_count, active_tracks in ((1.5, 1), (1, 0.5)):
            with self.subTest(
                detection_count=detection_count,
                active_tracks=active_tracks,
            ):
                with self.assertRaisesRegex(ValueError, "nonnegative integer"):
                    metrics.record_frame(
                        detection_count,  # type: ignore[arg-type]
                        active_tracks,  # type: ignore[arg-type]
                        1.0,
                        1.0,
                        1.0,
                    )
        with self.assertRaisesRegex(ValueError, "rolling window"):
            MetricsService(rolling_window_size=0)

    def test_concurrent_updates_and_snapshots_are_consistent(self) -> None:
        metrics = MetricsService(rolling_window_size=20)
        snapshots = []
        barrier = threading.Barrier(5)

        def writer() -> None:
            barrier.wait(timeout=5)
            for _ in range(100):
                metrics.record_frame(2, 1, 10.0, 20.0, 30.0)

        def reader() -> list:
            barrier.wait(timeout=5)
            return [metrics.get_snapshot() for _ in range(100)]

        with ThreadPoolExecutor(max_workers=5) as executor:
            writer_futures = [executor.submit(writer) for _ in range(4)]
            reader_future = executor.submit(reader)
            snapshots.extend(reader_future.result(timeout=10))
            for future in writer_futures:
                future.result(timeout=10)

        self.assertTrue(reader_future.done())
        self.assertTrue(all(future.done() for future in writer_futures))

        final = metrics.get_snapshot()
        self.assertEqual(final.frames_processed_total, 400)
        self.assertEqual(final.detections_total, 800)
        self.assertTrue(
            all(
                snapshot.detections_total == snapshot.frames_processed_total * 2
                for snapshot in snapshots
            )
        )


class MetricsConfigurationTests(unittest.TestCase):
    def test_default_and_environment_override(self) -> None:
        self.assertEqual(load_config({}).metrics.rolling_window_size, 60)
        config = load_config({"SMART_RETAIL_METRICS_ROLLING_WINDOW_SIZE": "12"})
        self.assertEqual(config.metrics.rolling_window_size, 12)

    def test_invalid_rolling_window_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "at least 1"):
            load_config({"SMART_RETAIL_METRICS_ROLLING_WINDOW_SIZE": "0"})


if __name__ == "__main__":
    unittest.main()
