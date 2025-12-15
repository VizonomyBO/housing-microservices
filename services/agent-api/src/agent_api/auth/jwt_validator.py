"""JWT validation helpers used by FastAPI dependencies."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from authlib.jose import JoseError, JsonWebKey, jwt
from fastapi import status

from agent_api.http.context import AuthContext
from agent_api.settings import AuthSettings
from telemetry import MetricsRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AuthValidationError(Exception):
    """Domain-specific error raised when JWT validation fails."""

    code: str
    message: str
    status_code: int = status.HTTP_401_UNAUTHORIZED


class _JWKSCache:
    def __init__(
        self,
        loader: Callable[[], Awaitable[dict[str, Any]]],
        *,
        ttl_seconds: int,
    ) -> None:
        self._loader = loader
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._expires_at = 0.0
        self._jwks: dict[str, Any] | None = None

    async def get(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._jwks and now < self._expires_at:
            return self._jwks
        async with self._lock:
            if self._jwks and time.monotonic() < self._expires_at:
                return self._jwks
            jwks = await self._loader()
            if not isinstance(jwks, dict) or "keys" not in jwks:
                raise AuthValidationError(
                    code="invalid_jwks",
                    message="JWKS response missing 'keys'",
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            self._jwks = jwks
            self._expires_at = time.monotonic() + self._ttl_seconds
            return jwks


class AuthTokenValidator:
    """Validates JWTs issued by auth-service and builds AuthContext objects."""

    def __init__(
        self,
        settings: AuthSettings,
        *,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._metrics = metrics
        self._allowed_algorithms = {alg.upper() for alg in settings.algorithms if alg}
        self._jwks_cache = (
            _JWKSCache(self._download_jwks, ttl_seconds=settings.cache_ttl_seconds)
            if settings.jwks_url
            else None
        )

    async def validate(self, token: str) -> AuthContext:
        """Validate the provided JWT and convert it into an AuthContext."""

        header = self._decode_header(token)
        algorithm = header.get("alg")
        if not algorithm:
            raise self._failure("missing_alg", "Token is missing 'alg' header")

        key = await self._select_key(algorithm, header.get("kid"))
        claims = self._decode_claims(token, key)
        payload = dict(claims)

        token_type = str(payload.get("type") or "access").lower()
        if token_type != "access":
            raise self._failure("invalid_type", "Token type must be 'access'")

        user_id = self._resolve_user_id(payload)
        scopes = self._extract_scopes(payload)
        roles = self._extract_roles(payload)

        if self._settings.required_scopes:
            required = set(self._settings.required_scopes)
            if not required.issubset(set(scopes)):
                raise self._failure(
                    "insufficient_scope",
                    "Token missing required scopes",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        tenant_id = self._resolve_tenant_id(payload)
        metadata = {
            "claims": payload,
            "kid": header.get("kid"),
            "alg": algorithm,
        }

        context = AuthContext(
            user_id=user_id,
            tenant_id=tenant_id,
            roles=roles,
            scopes=scopes,
            metadata=metadata,
        )
        self._record_event("success", reason=None)
        return context

    def _decode_claims(self, token: str, key: Any):
        options: dict[str, dict[str, Any]] = {
            "exp": {"essential": True},
            "iat": {"essential": True},
            "sub": {"essential": False},
        }
        if self._settings.issuer:
            options["iss"] = {"essential": True, "value": self._settings.issuer}
        if self._settings.audience:
            options["aud"] = {"essential": True, "value": self._settings.audience}
        try:
            claims = jwt.decode(token, key, claims_options=options)
            claims.validate(leeway=self._settings.leeway_seconds)
            return claims
        except JoseError as exc:  # pragma: no cover - authlib formats message
            raise self._failure("invalid_token", str(exc)) from exc

    async def _select_key(self, algorithm: str, kid: str | None) -> Any:
        if self._allowed_algorithms and algorithm.upper() not in self._allowed_algorithms:
            raise self._failure(
                "unsupported_alg",
                f"Algorithm {algorithm!r} not permitted",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if algorithm.upper().startswith("HS"):
            if not self._settings.shared_secret:
                raise self._failure(
                    "shared_secret_missing",
                    "AUTH_SHARED_SECRET is required for HS tokens",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            return self._settings.shared_secret

        if not self._jwks_cache:
            raise self._failure(
                "jwks_unavailable",
                "JWKS URL not configured for asymmetric tokens",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        jwks = await self._jwks_cache.get()
        keys = jwks.get("keys", [])
        selected: dict[str, Any] | None = None
        if kid:
            for entry in keys:
                if entry.get("kid") == kid:
                    selected = entry
                    break
        if not selected and keys:
            if len(keys) == 1:
                selected = keys[0]
            else:
                raise self._failure("unknown_kid", f"Signing key {kid!r} not found")
        if not selected:
            raise self._failure("empty_jwks", "No signing keys available")
        try:
            return JsonWebKey.import_key(selected)
        except (ValueError, JoseError) as exc:  # pragma: no cover - library-level failure
            raise self._failure("invalid_jwk", "Failed to load signing key") from exc

    def _decode_header(self, token: str) -> dict[str, Any]:
        try:
            header_b64 = token.split(".", 1)[0]
            padded = header_b64 + "=" * (-len(header_b64) % 4)
            data = base64.urlsafe_b64decode(padded)
            return json.loads(data)
        except (ValueError, json.JSONDecodeError) as exc:
            raise self._failure("malformed_header", "Unable to parse JWT header") from exc

    def _resolve_user_id(self, payload: dict[str, Any]) -> str:
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise self._failure("missing_sub", "Token missing subject/user identifier")
        raw = str(user_id)
        try:
            UUID(raw)
            return raw
        except ValueError:
            derived = uuid5(NAMESPACE_URL, raw)
            return str(derived)

    def _resolve_tenant_id(self, payload: dict[str, Any]) -> str | None:
        claim_name = self._settings.tenant_claim or "tenant_id"
        tenant_id = payload.get(claim_name)
        if tenant_id:
            return str(tenant_id)
        workspace_id = payload.get("workspace_id") or payload.get("account_id")
        if workspace_id:
            return str(workspace_id)
        return str(payload.get("user_id")) if payload.get("user_id") else None

    def _extract_scopes(self, payload: dict[str, Any]) -> list[str]:
        scopes: list[str] = []
        raw_scopes = payload.get("scopes")
        if isinstance(raw_scopes, list):
            scopes.extend(str(scope) for scope in raw_scopes if scope)
        raw_scope = payload.get(self._settings.scope_claim) or payload.get("scope")
        if isinstance(raw_scope, str):
            scopes.extend([segment for segment in raw_scope.split() if segment])
        roles = payload.get("roles")
        if isinstance(roles, list):
            scopes.extend(str(role) for role in roles if role)
        role = payload.get("role")
        if isinstance(role, str):
            scopes.append(role)
        if not scopes:
            scopes.append("agent-api:default")
        return list(dict.fromkeys(scopes))

    def _extract_roles(self, payload: dict[str, Any]) -> list[str]:
        roles = payload.get("roles")
        if isinstance(roles, list):
            return [str(role) for role in roles if role]
        role = payload.get("role")
        return [str(role)] if isinstance(role, str) and role else []

    def _failure(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_401_UNAUTHORIZED,
    ) -> AuthValidationError:
        self._record_event("failure", reason=code)
        logger.warning("auth.validation_failed", extra={"code": code, "detail": message})
        return AuthValidationError(code=code, message=message, status_code=status_code)

    def _record_event(self, event: str, *, reason: str | None) -> None:
        if self._metrics is not None:
            self._metrics.record_auth_event(event=event, reason=reason)

    async def _download_jwks(self) -> dict[str, Any]:
        assert self._settings.jwks_url is not None  # guarded by caller
        try:
            async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
                response = await client.get(self._settings.jwks_url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise self._failure(
                "jwks_http_error",
                f"JWKS endpoint returned {exc.response.status_code}",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        except httpx.HTTPError as exc:
            raise self._failure(
                "jwks_unreachable",
                "Unable to reach JWKS endpoint",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
