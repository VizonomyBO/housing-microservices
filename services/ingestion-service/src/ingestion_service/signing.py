from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any


def _canonicalize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    """Create an HMAC-SHA256 signature for the given payload."""

    data = _canonicalize(payload)
    digest = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def verify_signature(payload: dict[str, Any], signature: str, secret: str) -> bool:
    """Verify a signature matches the payload."""

    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)


def now_seconds() -> int:
    return int(time.time())

