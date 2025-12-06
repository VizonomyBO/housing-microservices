"""
Structured logging configuration for Lambda.
"""

import json
import logging
import os
import sys
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in Lambda."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "document_id"):
            log_data["document_id"] = record.document_id
        if hasattr(record, "error"):
            log_data["error"] = record.error

        # Add any extra attributes
        extra = getattr(record, "__dict__", {})
        for key in [
            "request_id",
            "document_id",
            "content_hash",
            "existing_document_id",
            "ingestion_id",
            "error",
        ]:
            if key in extra and key not in log_data:
                log_data[key] = extra[key]

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Set log level from environment
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))

    return logger


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds context to all log messages."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict]:
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs
