"""HTTP-friendly error helpers."""

from __future__ import annotations

from typing import Any


class GatewayError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def error_payload(
    *, code: str, message: str, request_id: str | None = None, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if request_id:
        payload["request_id"] = request_id
    if details:
        payload["error"]["details"] = details
    return payload


__all__ = ["GatewayError", "error_payload"]
