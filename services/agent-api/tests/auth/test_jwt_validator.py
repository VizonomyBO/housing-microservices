from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from authlib.jose import jwt

from agent_api.auth import AuthTokenValidator, AuthValidationError
from agent_api.settings import AuthSettings


def _build_settings(**overrides) -> AuthSettings:
    return AuthSettings(
        jwks_url=overrides.get("jwks_url"),
        issuer=overrides.get("issuer"),
        audience=overrides.get("audience"),
        algorithms=overrides.get("algorithms", ("HS256",)),
        cache_ttl_seconds=overrides.get("cache_ttl_seconds", 60),
        leeway_seconds=overrides.get("leeway_seconds", 0),
        required_scopes=overrides.get("required_scopes", ()),
        shared_secret=overrides.get("shared_secret", "demo-secret"),
        scope_claim=overrides.get("scope_claim", "scope"),
        tenant_claim=overrides.get("tenant_claim", "tenant_id"),
        http_timeout_seconds=overrides.get("http_timeout_seconds", 5.0),
    )


def _encode(payload: dict[str, object], secret: str = "demo-secret") -> str:
    header = {"alg": "HS256"}
    token = jwt.encode(header, payload, secret)
    return token.decode() if isinstance(token, bytes) else str(token)


@pytest.mark.asyncio
async def test_validator_produces_auth_context() -> None:
    expires = datetime.now(UTC) + timedelta(minutes=5)
    issued = datetime.now(UTC)
    payload = {
        "sub": "user-123",
        "exp": int(expires.timestamp()),
        "iat": int(issued.timestamp()),
        "scope": "agent:demo",
        "tenant_id": "tenant-321",
        "type": "access",
    }
    token = _encode(payload)
    validator = AuthTokenValidator(_build_settings())

    context = await validator.validate(token)

    assert context.user_id == "user-123"
    assert context.tenant_id == "tenant-321"
    assert "agent:demo" in context.scopes
    assert context.metadata["claims"]["sub"] == "user-123"


@pytest.mark.asyncio
async def test_validator_rejects_expired_token() -> None:
    timestamp = datetime.now(UTC) - timedelta(minutes=1)
    payload = {
        "sub": "user-123",
        "exp": int(timestamp.timestamp()),
        "iat": int((timestamp - timedelta(minutes=1)).timestamp()),
        "scope": "agent:demo",
        "type": "access",
    }
    token = _encode(payload)
    validator = AuthTokenValidator(_build_settings())

    with pytest.raises(AuthValidationError) as excinfo:
        await validator.validate(token)
    assert excinfo.value.code == "invalid_token"


@pytest.mark.asyncio
async def test_validator_rejects_signature_mismatch() -> None:
    expires = datetime.now(UTC) + timedelta(minutes=5)
    payload = {
        "sub": "user-123",
        "exp": int(expires.timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
        "scope": "agent:demo",
        "type": "access",
    }
    token = _encode(payload, secret="other-secret")
    validator = AuthTokenValidator(_build_settings(shared_secret="demo-secret"))

    with pytest.raises(AuthValidationError) as excinfo:
        await validator.validate(token)
    assert excinfo.value.code == "invalid_token"
