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
        
        # Add extra fields from record
        extra_fields = [
            "request_id",
            "trace_id",
            "ingestion_id",
            "document_id",
            "s3_key",
            "source_type",
            "content_hash",
            "existing_document_id",
            "error",
        ]
        
        extra = getattr(record, "__dict__", {})
        for key in extra_fields:
            if key in extra:
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


