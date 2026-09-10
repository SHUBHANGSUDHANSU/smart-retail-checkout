"""Tests for bounded, non-blocking realtime publication primitives."""

from __future__ import annotations

import unittest

from smart_retail.domain.events import CartEventType
from smart_retail.domain.models import CartSnapshot
from smart_retail.metrics import MetricsSnapshot
from smart_retail.realtime.broadcaster import (
    RealtimeBroadcaster,
    RealtimeClosedError,
)
from smart_retail.realtime.models import RealtimeCheckoutActivity, RealtimeEventType
from smart_retail.realtime.publisher import RealtimePublisher


class RealtimeBroadcasterTests(unittest.TestCase):
    def test_publish_delivers_the_same_immutable_message_to_every_subscriber(
        self,
    ) -> None:
        broadcaster = RealtimeBroadcaster(queue_capacity=4, clock=lambda: 101.5)
        first = broadcaster.subscribe()
        second = broadcaster.subscribe()
        cart = CartSnapshot(items=(), total=0)

        message = broadcaster.publish(RealtimeEventType.CART_UPDATED, cart)

        self.assertEqual(first.get_nowait(), message)
        self.assertEqual(second.get_nowait(), message)
        self.assertEqual(message.sequence, 1)
        self.assertEqual(message.timestamp, 101.5)
        self.assertIs(message.payload, cart)

    def test_full_subscriber_queue_discards_oldest_message_only_for_slow_client(
        self,
    ) -> None:
        broadcaster = RealtimeBroadcaster(queue_capacity=2)
        slow = broadcaster.subscribe()
        current = broadcaster.subscribe()
        payload = CartSnapshot(items=(), total=0)

        first = broadcaster.publish(RealtimeEventType.CART_UPDATED, payload)
        self.assertEqual(current.get_nowait(), first)
        second = broadcaster.publish(RealtimeEventType.CART_UPDATED, payload)
        self.assertEqual(current.get_nowait(), second)
        third = broadcaster.publish(RealtimeEventType.CART_UPDATED, payload)

        self.assertEqual(slow.get_nowait(), second)
        self.assertEqual(slow.get_nowait(), third)
        self.assertEqual(current.get_nowait(), third)

    def test_unsubscribe_and_close_release_subscribers_idempotently(self) -> None:
        broadcaster = RealtimeBroadcaster(queue_capacity=2)
        subscription = broadcaster.subscribe()
        self.assertEqual(broadcaster.subscriber_count, 1)

        broadcaster.unsubscribe(subscription)
        broadcaster.unsubscribe(subscription)
        self.assertTrue(subscription.closed)
        self.assertEqual(broadcaster.subscriber_count, 0)

        broadcaster.close()
        broadcaster.close()
        with self.assertRaises(RealtimeClosedError):
            broadcaster.subscribe()

    def test_sequences_increase_even_when_no_clients_are_connected(self) -> None:
        broadcaster = RealtimeBroadcaster(queue_capacity=1)
        payload = CartSnapshot(items=(), total=0)

        first = broadcaster.publish(RealtimeEventType.CART_UPDATED, payload)
        second = broadcaster.publish(RealtimeEventType.CART_UPDATED, payload)

        self.assertEqual((first.sequence, second.sequence), (1, 2))


class RealtimePublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 0.0
        self.broadcaster = RealtimeBroadcaster(queue_capacity=8)
        self.publisher = RealtimePublisher(
            self.broadcaster,
            metrics_interval_seconds=1.0,
            monotonic_clock=lambda: self.now,
        )
        self.subscription = self.publisher.subscribe()

    def test_cart_and_checkout_activity_publish_immediately(self) -> None:
        cart = CartSnapshot(items=(), total=0)
        activity = RealtimeCheckoutActivity(
            event_id=7,
            session_id=3,
            timestamp=100.0,
            track_id=14,
            product_id="bottle",
            event_type=CartEventType.ADD,
            unit_price=40,
        )

        self.publisher.publish_cart(cart)
        self.publisher.publish_checkout_event(activity)

        self.assertEqual(
            self.subscription.get_nowait().event_type,
            RealtimeEventType.CART_UPDATED,
        )
        self.assertEqual(
            self.subscription.get_nowait().payload,
            activity,
        )

    def test_metrics_publish_at_most_once_per_interval_with_latest_snapshot(
        self,
    ) -> None:
        first = metrics_snapshot(frames=1)
        second = metrics_snapshot(frames=2)
        third = metrics_snapshot(frames=3)

        self.assertTrue(self.publisher.publish_metrics_if_due(first))
        self.now = 0.5
        self.assertFalse(self.publisher.publish_metrics_if_due(second))
        self.now = 1.0
        self.assertTrue(self.publisher.publish_metrics_if_due(third))

        self.assertEqual(self.subscription.get_nowait().payload, first)
        self.assertEqual(self.subscription.get_nowait().payload, third)

    def test_close_ends_subscriptions_and_rejects_new_clients(self) -> None:
        self.publisher.close()
        self.publisher.close()

        self.assertTrue(self.subscription.closed)
        with self.assertRaises(RealtimeClosedError):
            self.publisher.subscribe()


def metrics_snapshot(frames: int) -> MetricsSnapshot:
    return MetricsSnapshot(
        frames_processed_total=frames,
        dropped_frames_total=0,
        detections_total=0,
        active_tracks=0,
        inference_latency_ms=0.0,
        frame_processing_latency_ms=0.0,
        current_fps=0.0,
        checkout_enter_events_total=0,
        checkout_exit_events_total=0,
        cart_additions_total=0,
        cart_removals_total=0,
        cart_resets_total=0,
        current_cart_items=0,
        current_cart_total=0,
        uptime_seconds=0.0,
        camera_errors_total=0,
        persistence_errors_total=0,
    )


if __name__ == "__main__":
    unittest.main()
