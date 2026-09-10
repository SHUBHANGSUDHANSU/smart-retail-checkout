"""Deterministic SSE encoding and stream-lifecycle tests."""

from __future__ import annotations

import json
import unittest
from collections import deque

from smart_retail.api.factory import create_api_app
from smart_retail.api.routes.realtime import encode_sse_message, stream_realtime_events
from smart_retail.domain.models import CartSnapshot
from smart_retail.realtime.broadcaster import RealtimeSubscription
from smart_retail.realtime.models import RealtimeEventType, RealtimeMessage


class _Request:
    def __init__(self, disconnected: bool = False) -> None:
        self.disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self.disconnected


class _Subscription:
    subscriber_id = 7

    def __init__(self, messages: list[RealtimeMessage]) -> None:
        self.messages = deque(messages)
        self.closed = False

    def get(self, timeout: float) -> RealtimeMessage | None:
        if self.messages:
            return self.messages.popleft()
        return None


class _Runtime:
    def __init__(self, messages: list[RealtimeMessage] | None = None) -> None:
        self.subscription = _Subscription(messages or [])
        self.unsubscribed = False

    def subscribe_realtime(self):
        return self.subscription

    def unsubscribe_realtime(self, subscription: RealtimeSubscription) -> None:
        self.unsubscribed = True
        subscription.closed = True

    def get_realtime_heartbeat_seconds(self) -> float:
        return 0.001


class RealtimeEncodingTests(unittest.TestCase):
    def test_encodes_named_sse_with_typed_json_envelope(self) -> None:
        message = RealtimeMessage(
            sequence=3,
            event_type=RealtimeEventType.CART_UPDATED,
            timestamp=1_700_000_000.0,
            payload=CartSnapshot(items=(), total=0),
        )

        encoded = encode_sse_message(message)

        lines = encoded.strip().splitlines()
        self.assertEqual(lines[0], "id: 3")
        self.assertEqual(lines[1], "event: cart.updated")
        payload = json.loads(lines[2].removeprefix("data: "))
        self.assertEqual(payload["sequence"], 3)
        self.assertEqual(payload["type"], "cart.updated")
        self.assertEqual(payload["payload"]["total"], 0)

    def test_stream_route_is_registered(self) -> None:
        application = create_api_app(_Runtime())

        operation = application.openapi()["paths"]["/api/v1/stream"]["get"]

        self.assertIn("realtime", operation["tags"])


class RealtimeStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_yields_application_message_and_cleans_up(self) -> None:
        message = RealtimeMessage(
            sequence=1,
            event_type=RealtimeEventType.CART_UPDATED,
            timestamp=1_700_000_000.0,
            payload=CartSnapshot(items=(), total=0),
        )
        runtime = _Runtime([message])
        stream = stream_realtime_events(_Request(), runtime)

        event = await anext(stream)
        await stream.aclose()

        self.assertIn("event: cart.updated", event)
        self.assertTrue(runtime.unsubscribed)

    async def test_yields_comment_heartbeat_without_fake_event(self) -> None:
        runtime = _Runtime()
        stream = stream_realtime_events(_Request(), runtime)

        event = await anext(stream)
        await stream.aclose()

        self.assertEqual(event, ": heartbeat\n\n")
        self.assertTrue(runtime.unsubscribed)

    async def test_disconnected_client_is_unsubscribed(self) -> None:
        runtime = _Runtime()
        events = [
            event async for event in stream_realtime_events(_Request(True), runtime)
        ]

        self.assertEqual(events, [])
        self.assertTrue(runtime.unsubscribed)


if __name__ == "__main__":
    unittest.main()
