"""Lifecycle tests for the background Uvicorn adapter."""

import logging
import unittest

from fastapi import FastAPI

from smart_retail.api.server import APIServerError, BackgroundAPIServer


class FakeThread:
    def __init__(self, alive_results: list[bool]) -> None:
        self._alive_results = iter(alive_results)
        self.join_calls = 0

    def join(self, timeout: float) -> None:
        self.join_calls += 1

    def is_alive(self) -> bool:
        return next(self._alive_results)


class BackgroundAPIServerTests(unittest.TestCase):
    def test_external_bind_emits_security_warning(self) -> None:
        with self.assertLogs(
            "smart_retail.api.server",
            level=logging.WARNING,
        ) as captured:
            BackgroundAPIServer(FastAPI(), "0.0.0.0", 8000)

        self.assertTrue(
            any(
                getattr(record, "event", None) == "api_externally_reachable"
                for record in captured.records
            )
        )

    def test_loopback_bind_does_not_emit_security_warning(self) -> None:
        with self.assertNoLogs(
            "smart_retail.api.server",
            level=logging.WARNING,
        ):
            BackgroundAPIServer(FastAPI(), "127.0.0.1", 8000)

    def test_stop_retains_timed_out_thread_for_retry(self) -> None:
        server = BackgroundAPIServer(FastAPI(), "127.0.0.1", 8000)
        thread = FakeThread([True, False])
        server._thread = thread  # type: ignore[assignment]

        with self.assertRaisesRegex(APIServerError, "did not stop"):
            server.stop()
        self.assertIs(server._thread, thread)
        server.stop()

        self.assertEqual(thread.join_calls, 2)
        self.assertIsNone(server._thread)

    def test_stop_without_started_thread_is_idempotent(self) -> None:
        server = BackgroundAPIServer(FastAPI(), "127.0.0.1", 8000)

        server.stop()
        server.stop()

        self.assertIsNone(server._thread)


if __name__ == "__main__":
    unittest.main()
