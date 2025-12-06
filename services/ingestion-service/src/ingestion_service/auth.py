from __future__ import annotations

import httpx
import jwt
from pydantic import BaseModel

from ingestion_service.settings import Settings


class UserContext(BaseModel):
    user_id: str
    email: str | None = None
    username: str | None = None
    country_code: str | None = None


class AuthError(Exception):
    """Raised when token validation fails."""


def _parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise AuthError("Authorization header must be Bearer")
    return authorization.split(" ", 1)[1].strip()


def _decode_locally(token: str, settings: Settings) -> UserContext:
    secret = settings.jwt_secret_key
    if not secret:
        raise AuthError("JWT secret not configured")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc

    token_type = payload.get("type")
    if token_type and token_type != "access":
        raise AuthError("Invalid token type")

    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        raise AuthError("Token missing user_id")

    return UserContext(
        user_id=str(user_id),
        email=payload.get("email"),
        username=payload.get("username"),
        country_code=payload.get("country_code"),
    )


async def _verify_remote(token: str, settings: Settings) -> UserContext:
    if not settings.auth_base_url:
        raise AuthError("Auth service URL not configured")
    verify_url = f"{str(settings.auth_base_url).rstrip('/')}{settings.auth_verify_path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(verify_url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise AuthError(f"Token verification failed: {resp.text}")
    data = resp.json()
    user_id = data.get("user_id")
    if not user_id:
        raise AuthError("Auth response missing user_id")
    return UserContext(
        user_id=str(user_id),
        email=data.get("email"),
        username=data.get("username"),
        country_code=data.get("country_code"),
    )


async def verify_token(authorization: str | None, settings: Settings) -> UserContext:
    """Validate a bearer token using local JWT secret or remote auth-service."""

    token = _parse_bearer_token(authorization)
    if settings.jwt_secret_key:
        return _decode_locally(token, settings)
    return await _verify_remote(token, settings)

