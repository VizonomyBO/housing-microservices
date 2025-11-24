"""
Flask decorators for authentication and authorization
"""

import json
import logging
import os
import urllib.error
import urllib.request
from functools import wraps
from typing import cast

from flask import current_app, g, jsonify, request

logger = logging.getLogger(__name__)

ERROR_NO_TOKEN = "Authentication required"
ERROR_INVALID_TOKEN = "Invalid or expired token"
ERROR_TOKEN_VERIFICATION_FAILED = "Token verification failed"
ERROR_AUTH_SERVICE_UNAVAILABLE = "Auth service unavailable"

# Default auth service URL (for internal calls)
DEFAULT_AUTH_SERVICE_URL = "http://localhost:5001"
DEFAULT_HTTP_TIMEOUT = 5.0


def _extract_token_from_request() -> str | None:
    """Extract token from Authorization header, cookies, or JSON body."""
    # Try Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]

    # Fallback to cookie
    token = request.cookies.get("access_token")
    if token:
        return token

    # Fallback to request body
    data = request.get_json() if request.is_json else {}
    if data:
        body_token = data.get("token") or data.get("access_token")
        if body_token:
            return str(body_token)

    return None


def _get_auth_service_url() -> str:
    """Get auth service URL from config or environment."""
    try:
        return cast(
            str,
            current_app.config.get(
                "AUTH_SERVICE_URL", os.getenv("AUTH_SERVICE_URL", DEFAULT_AUTH_SERVICE_URL)
            ),
        )
    except RuntimeError:
        return os.getenv("AUTH_SERVICE_URL", DEFAULT_AUTH_SERVICE_URL)


def _verify_token_direct(token: str) -> tuple[dict | None, str | None]:
    """
    Verify token directly using token_validator (for same-service use).

    Returns:
        Tuple of (response_data, None) on success or (None, error_message) on failure
    """
    try:
        from app.utils.token_validator import create_validation_response, verify_token_direct

        payload, error = verify_token_direct(token)
        if error or payload is None:
            return None, error or ERROR_INVALID_TOKEN

        # Convert to same format as HTTP endpoint response
        response_data = create_validation_response(payload)
        return response_data, None
    except Exception as e:
        logger.exception(
            "Unexpected error during direct token verification", extra={"error": str(e)}
        )
        return None, ERROR_TOKEN_VERIFICATION_FAILED


def _verify_token_via_http(token: str) -> tuple[dict | None, str | None]:
    """
    Verify token via HTTP call to /v1/auth/verify-token endpoint.
    Used when calling from a different service.

    Returns:
        Tuple of (response_data, None) on success or (None, error_message) on failure
    """
    auth_service_url = _get_auth_service_url()
    verify_url = f"{auth_service_url}/v1/auth/verify-token"
    data = json.dumps({"token": token}).encode("utf-8")
    req = urllib.request.Request(
        verify_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as response:
            if response.status == 200:
                response_data = json.loads(response.read().decode("utf-8"))
                if response_data.get("valid"):
                    return response_data, None
                error_msg = response_data.get("error", ERROR_INVALID_TOKEN)
                return None, error_msg
            if response.status == 401:
                error_data = json.loads(response.read().decode("utf-8"))
                return None, error_data.get("error", ERROR_INVALID_TOKEN)
            logger.error(
                "Unexpected response from verify-token endpoint",
                extra={"status": response.status},
            )
            return None, ERROR_TOKEN_VERIFICATION_FAILED

    except urllib.error.HTTPError as e:
        if e.code == 401:
            try:
                error_data = json.loads(e.read().decode("utf-8"))
                return None, error_data.get("error", ERROR_INVALID_TOKEN)
            except Exception:
                return None, ERROR_INVALID_TOKEN
        logger.error(
            "HTTP error from verify-token endpoint", extra={"status": e.code, "path": request.path}
        )
        return None, ERROR_TOKEN_VERIFICATION_FAILED

    except urllib.error.URLError as e:
        logger.error(
            "Failed to connect to verify-token endpoint",
            extra={"error": str(e), "path": request.path},
        )
        return None, ERROR_AUTH_SERVICE_UNAVAILABLE

    except Exception as e:
        logger.exception("Unexpected error during token verification", extra={"error": str(e)})
        return None, ERROR_TOKEN_VERIFICATION_FAILED


def _inject_user_context(response_data: dict) -> None:
    """Inject user context from response into Flask's g."""
    g.user_id = response_data.get("user_id")
    g.user_roles = response_data.get("roles", [])
    g.user_country_code = response_data.get("country_code", "USA")
    g.user_username = response_data.get("username")
    g.user_email = response_data.get("email")
    g.token_payload = response_data


def require_auth(f):
    """
    Decorator to require valid JWT token for Flask endpoints.

    Extracts token from Authorization header, cookies, or JSON body,
    verifies it via the /v1/auth/verify-token HTTP endpoint, and injects
    user context into Flask's g (application context).

    Usage:
        @auth_bp.route("/protected", methods=["POST"])
        @require_auth
        def protected_endpoint():
            user_id = g.user_id
            roles = g.user_roles
            # ... endpoint logic ...
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Extract token from request
        token = _extract_token_from_request()
        if not token:
            logger.warning("Authentication required: missing token", extra={"path": request.path})
            return jsonify({"error": ERROR_NO_TOKEN}), 401

        # Verify token directly (same-service optimization)
        # Falls back to HTTP if direct verification fails
        response_data, error = _verify_token_direct(token)
        if error or response_data is None:
            # Fallback to HTTP verification (for cross-service scenarios)
            response_data, error = _verify_token_via_http(token)
            if error or response_data is None:
                logger.warning(
                    "Token verification failed",
                    extra={"path": request.path, "error": error or ERROR_INVALID_TOKEN},
                )
                status_code = 503 if error == ERROR_AUTH_SERVICE_UNAVAILABLE else 401
                return jsonify({"error": error or ERROR_INVALID_TOKEN}), status_code

        _inject_user_context(response_data)

        return f(*args, **kwargs)

    return decorated_function
