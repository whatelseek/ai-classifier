"""Structured logging configuration and request-scoped correlation IDs."""

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to JSON.

        Args:
            record: Standard library log record.

        Returns:
            UTF-8 JSON string containing message, level, and optional fields.
        """
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            payload.update(record.extra_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Configure root logging handlers and formatters.

    Args:
        level: Minimum log level name (e.g. ``INFO``).
        json_logs: When True, emit JSON lines; otherwise use plain text.
    """
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_extra(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Emit a log record with arbitrary structured fields.

    Args:
        logger: Target logger.
        level: ``logging`` level constant.
        message: Human-readable message.
        **fields: Additional keys merged into the JSON payload.
    """
    record = logger.makeRecord(logger.name, level, "", 0, message, (), None)
    record.extra_fields = fields  # type: ignore[attr-defined]
    logger.handle(record)