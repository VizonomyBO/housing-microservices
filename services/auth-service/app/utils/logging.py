"""Logging configuration for the authentication service."""

import logging
import os
import sys


def _parse_log_level(level_str: str) -> int:
    """Parse log level string to logging level constant."""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str.upper(), logging.INFO)


def configure_logging() -> logging.Logger:
    """Configure and return the centralized application logger."""
    # Create the main application logger
    app_logger = logging.getLogger("auth_service")

    # Avoid adding multiple handlers if already configured
    if app_logger.handlers:
        return app_logger

    # Set log level from environment variable
    log_level = _parse_log_level(os.getenv("LOG_LEVEL", "INFO"))

    app_logger.setLevel(log_level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # Add handler to logger
    app_logger.addHandler(console_handler)

    # Prevent propagation to root logger to avoid duplicate logs
    app_logger.propagate = False

    return app_logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a child logger of the application logger."""
    app_logger = configure_logging()
    if name:
        return app_logger.getChild(name)
    return app_logger


# Global application logger instance
app_logger = configure_logging()
