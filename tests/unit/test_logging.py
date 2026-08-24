"""Tests for structured formatting and process logging configuration."""

import io
import json
import logging
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from smart_retail.infrastructure.logging_config import (
    EventFormatter,
    JsonEventFormatter,
    log_event,
)


class StructuredLoggingTests(unittest.TestCase):
    def make_stream_logger(
        self,
        formatter: logging.Formatter,
        level: int = logging.DEBUG,
    ) -> tuple[logging.Logger, io.StringIO]:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        logger = logging.Logger(f"test.observability.{id(stream)}", level=level)
        logger.propagate = False
        logger.addHandler(handler)
        return logger, stream

    def test_readable_formatter_includes_named_fields(self) -> None:
        logger, stream = self.make_stream_logger(
            EventFormatter("%(levelname)s | %(name)s | %(message)s")
        )

        log_event(
            logger,
            logging.INFO,
            "cart_item_added",
            "Cart item added",
            track_id=14,
            product="Water Bottle",
            quantity=1,
            cart_total=120,
        )

        output = stream.getvalue()
        self.assertIn('event="cart_item_added"', output)
        self.assertIn("track_id=14", output)
        self.assertIn('product="Water Bottle"', output)
        self.assertNotIn("tensor", output.lower())

    def test_json_formatter_emits_parseable_flat_event(self) -> None:
        logger, stream = self.make_stream_logger(JsonEventFormatter())

        log_event(
            logger,
            logging.WARNING,
            "camera_read_recovered",
            "Camera frame reads recovered",
            camera_index=0,
            failed_attempts=2,
        )

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["level"], "WARNING")
        self.assertEqual(payload["event"], "camera_read_recovered")
        self.assertEqual(payload["camera_index"], 0)
        self.assertEqual(payload["failed_attempts"], 2)
        self.assertTrue(payload["timestamp"].endswith("Z"))

    def test_unexpected_exception_includes_traceback(self) -> None:
        logger, stream = self.make_stream_logger(JsonEventFormatter())

        try:
            raise RuntimeError("unexpected test failure")
        except RuntimeError:
            log_event(
                logger,
                logging.ERROR,
                "application_runtime_failed",
                "Unexpected application failure",
                exc_info=True,
            )

        payload = json.loads(stream.getvalue())
        self.assertIn("RuntimeError: unexpected test failure", payload["exception"])
        self.assertIn("Traceback", payload["exception"])

    def test_debug_events_are_filtered_at_info_level(self) -> None:
        logger, stream = self.make_stream_logger(
            EventFormatter("%(levelname)s | %(message)s"),
            level=logging.INFO,
        )

        log_event(logger, logging.DEBUG, "frame_diagnostic", "Frame processed")
        log_event(logger, logging.INFO, "application_started", "Application started")

        output = stream.getvalue()
        self.assertNotIn("frame_diagnostic", output)
        self.assertIn("application_started", output)

    def test_file_logging_uses_bounded_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "smart-retail.log"
            project_root = Path(__file__).parents[2]
            child_script = """
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))

from smart_retail.config import LoggingConfig
from smart_retail.infrastructure.logging_config import configure_logging, log_event

log_path = Path(sys.argv[1])
logger = configure_logging(
    LoggingConfig(
        level="INFO",
        json_enabled=True,
        file_path=log_path,
        file_max_bytes=2048,
        file_backup_count=2,
    )
)
file_handlers = [
    handler
    for handler in logging.getLogger().handlers
    if isinstance(handler, RotatingFileHandler)
]
if len(file_handlers) != 1:
    raise AssertionError(f"expected one rotating handler, got {len(file_handlers)}")

log_event(
    logger,
    logging.INFO,
    "application_started",
    "Application started",
)
file_handlers[0].flush()
payload = json.loads(log_path.read_text(encoding="utf-8"))
print(
    json.dumps(
        {
            "handler_count": len(file_handlers),
            "max_bytes": file_handlers[0].maxBytes,
            "backup_count": file_handlers[0].backupCount,
            "file_event": payload["event"],
        }
    )
)
"""

            completed = subprocess.run(
                [sys.executable, "-c", child_script, str(log_path)],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["handler_count"], 1)
            self.assertEqual(summary["max_bytes"], 2048)
            self.assertEqual(summary["backup_count"], 2)
            self.assertEqual(summary["file_event"], "application_started")
            self.assertIn("application_started", completed.stderr)


if __name__ == "__main__":
    unittest.main()
