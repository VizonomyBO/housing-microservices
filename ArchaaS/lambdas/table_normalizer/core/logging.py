"""Structured logging for table-normalizer Lambda."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional


class StructuredLogger:
    """JSON-formatted structured logger for Lambda."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        self.logger.handlers = []
        
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)
        
        self._request_id: Optional[str] = None
    
    def set_request_id(self, request_id: str) -> None:
        self._request_id = request_id
    
    def _log(
        self,
        level: int,
        message: str,
        extra: Optional[dict] = None,
        exc_info: bool = False,
    ) -> None:
        log_data = extra or {}
        log_data["request_id"] = self._request_id
        
        self.logger.log(level, message, extra={"structured": log_data}, exc_info=exc_info)
    
    def info(self, message: str, extra: Optional[dict] = None) -> None:
        self._log(logging.INFO, message, extra)
    
    def warning(self, message: str, extra: Optional[dict] = None) -> None:
        self._log(logging.WARNING, message, extra)
    
    def error(
        self,
        message: str,
        extra: Optional[dict] = None,
        exc_info: bool = False,
    ) -> None:
        self._log(logging.ERROR, message, extra, exc_info)
    
    def debug(self, message: str, extra: Optional[dict] = None) -> None:
        self._log(logging.DEBUG, message, extra)


class JsonFormatter(logging.Formatter):
    """JSON log formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if hasattr(record, "structured"):
            log_entry.update(record.structured)
        
        if record.exc_info:
            import traceback
            log_entry["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            )
        
        return json.dumps(log_entry)


_loggers: dict[str, StructuredLogger] = {}


def get_logger(name: str) -> StructuredLogger:
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]

