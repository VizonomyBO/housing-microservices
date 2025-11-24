"""
Direct token validation without HTTP overhead.

This module provides functions for validating JWT tokens directly,
avoiding the need for HTTP calls to /auth/verify-token endpoint.
"""

import os
from typing import TYPE_CHECKING

import jwt

from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.config import Config

logger = get_logger(__name__)

TokenPayload = dict[str, object]
ValidationResult = tuple[TokenPayload | None, str | None]


def _get_jwt_secret_key(config: "Config | None" = None) -> str:
    """Get JWT secret key from config or environment"""
    if config:
        return config.JWT_SECRET_KEY
    # Try Flask context (for backward compatibility)
    try:
        from flask import current_app

        return str(current_app.config["JWT_SECRET_KEY"])
    except RuntimeError:
        # Not in Flask context - try environment
        secret_key = os.getenv("JWT_SECRET_KEY")
        if not secret_key:
            raise ValueError("JWT_SECRET_KEY not configured") from None
        return str(secret_key)


def verify_token_direct(token: str, config: "Config | None" = None) -> ValidationResult:
    """
    Verify JWT token directly without HTTP call.

    This function provides the same validation as /auth/verify-token endpoint
    but without HTTP overhead. Can be used by middleware in the same service
    or imported by other services.

    Args:
        token: JWT token string
        config: Optional config object (for FastAPI)

    Returns:
        Tuple of (payload_dict, None) on success or (None, error_message) on failure

    Example:
        >>> payload, error = verify_token_direct(token)
        >>> if error:
        >>>     return {"error": error}, 401
        >>> user_id = payload["user_id"]
    """
    try:
        # Get JWT secret from config or environment
        try:
            secret_key = _get_jwt_secret_key(config)
        except ValueError as e:
            logger.error(f"JWT_SECRET_KEY not configured: {e}")
            return None, "Token verification configuration error"

        # Decode and verify token
        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            logger.warning("Token verification failed: token expired")
            return None, "Token has expired"
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token verification failed: invalid token - {e!s}")
            return None, "Invalid token"

        # Verify token type
        if payload.get("type") != "access":
            logger.warning(
                "Token verification failed: invalid token type",
                extra={"token_type": payload.get("type")},
            )
            return None, "Invalid token type"

        # Token payload is sufficient for validation
        # User data enrichment (if needed) should be done at the endpoint level with a session

        logger.debug("Token verified successfully", extra={"user_id": payload.get("user_id")})
        return payload, None

    except Exception as e:
        logger.exception("Unexpected error during token verification", extra={"error": str(e)})
        return None, "Token verification failed"


def verify_token_with_secret(token: str, secret_key: str) -> ValidationResult:
    """
    Verify JWT token with explicit secret key (for services without Flask context).

    Args:
        token: JWT token string
        secret_key: JWT secret key

    Returns:
        Tuple of (payload_dict, None) on success or (None, error_message) on failure
    """
    try:
        # Decode and verify token
        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return None, "Token has expired"
        except jwt.InvalidTokenError:
            return None, "Invalid token"

        # Verify token type
        if payload.get("type") != "access":
            return None, "Invalid token type"

        # Note: Without database access, we can't enrich with current user data
        # Services using this function should handle that separately if needed

        return payload, None

    except Exception as e:
        logger.exception("Unexpected error during token verification", extra={"error": str(e)})
        return None, "Token verification failed"


def create_validation_response(payload: TokenPayload) -> dict[str, object]:
    """
    Create validation response in the same format as /auth/verify-token endpoint.

    This ensures compatibility between direct function calls and HTTP endpoint.

    Args:
        payload: Token payload dictionary

    Returns:
        Response dictionary matching /auth/verify-token format
    """
    return {
        "valid": True,
        "user_id": payload.get("user_id"),
        "username": payload.get("username"),
        "email": payload.get("email"),
        "role": payload.get("role"),
        "roles": payload.get("roles", [payload.get("role")] if payload.get("role") else []),
        "country_code": payload.get("country_code"),
    }
