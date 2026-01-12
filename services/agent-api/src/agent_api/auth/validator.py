"""JWT validation utilities for the Agent API."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from jose import ExpiredSignatureError, JWTError, jwt

from agent_api.settings import AuthSettings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AuthContext:
    user_id: str | None
    tenant_id: str | None = None
    roles: list[str] | None = None
    scopes: list[str] | None = None
    metadata: dict[str, Any] | None = None


class AuthValidationError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthTokenValidator:
    """Validates JWTs issued by auth-service (JWKS or shared secret)."""

    def __init__(self, settings: AuthSettings):
        self._settings = settings
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_expires_at: datetime | None = None

    async def validate(self, token: str) -> AuthContext:
        options = {"verify_aud": bool(self._settings.audience)}
        algorithms = list(self._settings.algorithms)
        shared_secret = (self._settings.shared_secret or "").strip()
        try:
            if shared_secret:
                claims = jwt.decode(
                    token,
                    key=shared_secret,
                    algorithms=algorithms,
                    audience=self._settings.audience,
                    issuer=self._settings.issuer,
                    options=options,
                )
            else:
                claims = jwt.decode(
                    token,
                    key=self._get_key,
                    algorithms=algorithms,
                    audience=self._settings.audience,
                    issuer=self._settings.issuer,
                    options=options,
                )
        except ExpiredSignatureError as exc:
            raise AuthValidationError("Token expired", status_code=401) from exc
        except JWTError as exc:
            raise AuthValidationError("Invalid token", status_code=401) from exc

        scopes = _split_scopes(claims.get(self._settings.scope_claim))
        _enforce_required_scopes(scopes, self._settings.required_scopes)

        user_id = claims.get("sub") or claims.get("user_id")
        tenant_id = claims.get(self._settings.tenant_claim) if self._settings.tenant_claim else None
        roles = _split_scopes(claims.get("roles"))
        return AuthContext(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes,
            roles=roles,
            metadata=claims,
        )

    def _get_key(self, unverified_header: dict[str, Any], payload: dict[str, Any]) -> str:
        if self._settings.shared_secret:
            return self._settings.shared_secret
        if not self._settings.jwks_url:
            raise AuthValidationError("No JWKS configured for token validation", status_code=503)
        jwks = self._load_jwks()
        kid = unverified_header.get("kid")
        if kid and "keys" in jwks:
            for key in jwks["keys"]:
                if key.get("kid") == kid:
                    return json.dumps(key)
        raise AuthValidationError("Unable to resolve signing key", status_code=401)

    def _load_jwks(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        if self._jwks_cache and self._jwks_expires_at and now < self._jwks_expires_at:
            return self._jwks_cache

        timeout = httpx.Timeout(self._settings.http_timeout_seconds)
        with httpx.Client(timeout=timeout) as client:
            response = client.get(self._settings.jwks_url or "")
            response.raise_for_status()
            jwks = response.json()

        self._jwks_cache = jwks
        self._jwks_expires_at = now + timedelta(seconds=self._settings.cache_ttl_seconds)
        return jwks


def _split_scopes(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [segment for segment in raw.replace(",", " ").split() if segment]
    if isinstance(raw, list | tuple):
        return [str(item) for item in raw if item]
    return []


def _enforce_required_scopes(scopes: list[str], required: tuple[str, ...]) -> None:
    missing = [scope for scope in required if scope and scope not in scopes]
    if missing:
        joined = ", ".join(sorted(missing))
        raise AuthValidationError(f"Missing required scopes: {joined}", status_code=403)


__all__ = ["AuthContext", "AuthTokenValidator", "AuthValidationError"]
