"""Error types for reduced E2E smoke automation."""

from __future__ import annotations


class SmokeError(RuntimeError):
    """Raised when an automation stage fails."""

    def __init__(self, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.context = context or {}


__all__ = ["SmokeError"]
