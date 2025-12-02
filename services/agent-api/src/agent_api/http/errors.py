"""Error helpers shared by FastAPI routes and middleware."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GatewayError(Exception):
    """Structured error compatible with the documented envelope."""

    code: str
    message: str
    status_code: int = 500
    details: dict[str, Any] | None = None


def error_payload(
    *, code: str, message: str, request_id: str | None, details: Any | None = None
) -> dict[str, Any]:
    """Return the canonical error envelope for API responses."""

    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }


__all__ = ["GatewayError", "error_payload"]
