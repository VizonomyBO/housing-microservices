"""
Direct token validation helper used by AuthMiddleware.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import jwt

from app.db import get_session
from app.models.user import User
from app.utils.logging import get_logger

logger = get_logger(__name__)

TokenPayload = dict[str, Any]
ValidationResult = tuple[TokenPayload | None, str | None]


def _get_secret_key() -> str | None:
    """Get JWT secret key from environment"""
    return os.getenv("JWT_SECRET_KEY")


def verify_token_direct(token: str) -> ValidationResult:
    """
    Validate a JWT token without an HTTP roundtrip to auth-service.
    """

    secret = _get_secret_key()
    if not secret:
        logger.error("JWT secret key is not configured")
        return None, "Token verification configuration error"

    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired during direct validation")
        return None, "Token has expired"
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid token during direct validation: %s", exc)
        return None, "Invalid token"

    if payload.get("type") not in (None, "access"):
        return None, "Invalid token type"

    # Preserve roles from token - they take precedence
    token_roles = payload.get("roles")
    token_role = payload.get("role")
    if not token_roles and token_role:
        token_roles = [token_role] if isinstance(token_role, str) else token_role
    if not token_roles:
        token_roles = []

    user_id = payload.get("user_id")
    user_uuid = None
    if user_id is not None:
        try:
            user_uuid = uuid.UUID(str(user_id))
            payload["user_id"] = str(user_uuid)
        except (ValueError, TypeError):
            logger.warning("Token payload contained invalid user_id", extra={"user_id": user_id})

    if user_uuid is not None:
        session = get_session()
        try:
            user = session.query(User).filter_by(user_id=user_uuid).first()
            if user:
                # Enrich payload with database data, but preserve roles from token
                payload.setdefault("username", user.username)
                payload.setdefault("email", user.email)
                if "country_code" not in payload or not payload.get("country_code"):
                    payload["country_code"] = user.country_code
                # Only set role/roles from DB if not in token
                if not token_roles and user.role:
                    payload["role"] = user.role
                    payload["roles"] = [user.role]
                else:
                    # Preserve token roles
                    payload["roles"] = (
                        token_roles if isinstance(token_roles, list) else [token_roles]
                    )
                    if token_role:
                        payload["role"] = token_role
            else:
                logger.warning(
                    "User not found for token payload, using token data",
                    extra={"user_id": str(user_uuid)},
                )
                # Use roles from token
                payload["roles"] = (
                    token_roles
                    if isinstance(token_roles, list)
                    else [token_roles]
                    if token_roles
                    else []
                )
        finally:
            session.close()
    else:
        # Ensure roles is set even if user_id is missing/invalid
        payload["roles"] = (
            token_roles if isinstance(token_roles, list) else [token_roles] if token_roles else []
        )

    return payload, None


def create_validation_response(payload: TokenPayload) -> dict[str, Any]:
    return {
        "valid": True,
        "user_id": payload.get("user_id"),
        "username": payload.get("username"),
        "email": payload.get("email"),
        "role": payload.get("role"),
        "roles": payload.get("roles", []),
        "country_code": payload.get("country_code"),
    }
