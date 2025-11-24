"""
Authentication utilities for user-service.
Validates tokens by calling auth-service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    """User context extracted from JWT token"""

    user_id: int
    roles: list[str]
    country_code: str
    username: str | None = None
    email: str | None = None


async def validate_token(request: Request, auth_service_url: str) -> UserContext:
    """
    Validate JWT token by calling auth-service.

    Args:
        request: FastAPI request object
        auth_service_url: URL of auth-service

    Returns:
        UserContext if token is valid

    Raises:
        HTTPException: If token is missing or invalid
    """
    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token"
        )

    parts = auth_header.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header"
        )

    token = parts[1]

    # Call auth-service to validate token
    try:
        timeout = httpx.Timeout(5.0, connect=2.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{auth_service_url}/v1/auth/verify-token",
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                if data.get("valid"):
                    return UserContext(
                        user_id=data.get("user_id"),
                        roles=data.get("roles", [data.get("role")] if data.get("role") else []),
                        country_code=data.get("country_code", "USA"),
                        username=data.get("username"),
                        email=data.get("email"),
                    )

            # Token validation failed
            error_msg = "Invalid or expired token"
            if response.status_code == status.HTTP_401_UNAUTHORIZED:
                error_data = (
                    response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                error_msg = error_data.get("error", error_msg)

            logger.warning("Token validation failed", extra={"status_code": response.status_code})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_msg)

    except httpx.TimeoutException as e:
        logger.error("Auth service timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable"
        ) from e
    except httpx.RequestError as e:
        logger.error("Auth service request error", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable"
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during token validation", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Token validation failed"
        ) from e
