"""Process-level human-readable and JSON-friendly logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

from smart_retail.config import LoggingConfig

EVENT_ATTRIBUTE = "event"
EVENT_FIELDS_ATTRIBUTE = "event_fields"


class EventFormatter(logging.Formatter):
    """Append stable event names and fields to readable development logs."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        event = getattr(record, EVENT_ATTRIBUTE, None)
        fields = getattr(record, EVENT_FIELDS_ATTRIBUTE, {})
        details: list[str] = []
        if event:
            details.append(f"event={json.dumps(event, ensure_ascii=False)}")
        details.extend(
            f"{key}={json.dumps(value, ensure_ascii=False, default=str)}"
            for key, value in sorted(fields.items())
        )
        return f"{rendered} | {' '.join(details)}" if details else rendered


class JsonEventFormatter(logging.Formatter):
    """Render one JSON object per record for ingestion by log tooling."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc)
        payload: dict[str, Any] = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace(
                "+00:00",
                "Z",
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, EVENT_ATTRIBUTE, None)
        if event:
            payload["event"] = event
        for key, value in getattr(record, EVENT_FIELDS_ATTRIBUTE, {}).items():
            output_key = f"field_{key}" if key in payload else key
            payload[output_key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    *,
    exc_info: bool = False,
    **fields: object,
) -> None:
    """Write a named event with small, explicitly selected structured fields."""
    logger.log(
        level,
        message,
        exc_info=exc_info,
        extra={EVENT_ATTRIBUTE: event, EVENT_FIELDS_ATTRIBUTE: fields},
    )


def configure_logging(config: LoggingConfig) -> logging.Logger:
    """Configure console and optional rotating-file logging for the process."""
    formatter: logging.Formatter
    if config.json_enabled:
        formatter = JsonEventFormatter()
    else:
        formatter = EventFormatter(config.format, datefmt="%H:%M:%S")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [console_handler]
    if config.file_path is not None:
        config.file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            config.file_path,
            maxBytes=config.file_max_bytes,
            backupCount=config.file_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    _replace_root_handlers(handlers, getattr(logging, config.level))
    logging.captureWarnings(True)
    return logging.getLogger("smart_retail.app")


def configure_bootstrap_logging() -> logging.Logger:
    """Provide safe stderr logging when normal configuration cannot be loaded."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        EventFormatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    _replace_root_handlers([handler], logging.INFO)
    return logging.getLogger("smart_retail.app")


def _replace_root_handlers(
    handlers: list[logging.Handler],
    level: int,
) -> None:
    root_logger = logging.getLogger()
    for old_handler in root_logger.handlers[:]:
        root_logger.removeHandler(old_handler)
        old_handler.close()
    root_logger.setLevel(level)
    for handler in handlers:
        root_logger.addHandler(handler)
