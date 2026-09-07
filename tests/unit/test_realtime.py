"""Tests for bounded, non-blocking realtime publication primitives."""

from __future__ import annotations

import unittest

from smart_retail.domain.models import CartSnapshot
from smart_retail.realtime.broadcaster import (
    RealtimeBroadcaster,
    RealtimeClosedError,
)
from smart_retail.realtime.models import RealtimeEventType


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


if __name__ == "__main__":
    unittest.main()
