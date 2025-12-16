from __future__ import annotations

import os
import time

from authlib.jose import jwt


def make_auth_header(
    user_id: str,
    *,
    tenant_id: str | None = None,
    scopes: list[str] | None = None,
    expires_in_seconds: int = 3600,
) -> dict[str, str]:
    """Build a signed HS256 JWT header for test requests."""

    secret = os.getenv("AUTH_SHARED_SECRET")
    if not secret:
        raise RuntimeError("AUTH_SHARED_SECRET is required to mint test tokens")
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if scopes:
        payload["scope"] = " ".join(scopes)
    header = {"alg": "HS256"}
    token = jwt.encode(header, payload, secret)
    if isinstance(token, bytes):
        token = token.decode()
    return {"Authorization": f"Bearer {token}"}


__all__ = ["make_auth_header"]
