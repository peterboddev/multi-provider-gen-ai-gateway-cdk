"""Structured JSON logging configuration for the gateway."""

import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Format log records as JSON with standard fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def configure_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the gateway.

    Sets up the 'gateway' logger with a StreamHandler using JSONFormatter,
    ensuring all gateway log output is JSON-formatted.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger("gateway")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(handler)
    root_logger.propagate = False
