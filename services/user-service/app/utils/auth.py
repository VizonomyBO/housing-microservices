"""
Authentication utilities for JWT token validation via auth-service
"""
import logging
from functools import wraps
from typing import Optional, Dict, Any, Tuple, Callable, cast

from flask import request, jsonify, current_app
import requests

logger = logging.getLogger(__name__)

# Type definitions
TokenPayload = Dict[str, Any]
TokenResponse = Tuple[Optional[TokenPayload], Optional[str]]


def get_token_from_header() -> Optional[str]:
    """Extract JWT token from Authorization header, with fallback to cookies and request body"""
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
    if request.is_json:
        data = request.get_json()
        if data and "token" in data:
            token_value = data.get("token")
            return cast(Optional[str], token_value) if isinstance(token_value, str) else None
        if data and "access_token" in data:
            token_value = data.get("access_token")
            return cast(Optional[str], token_value) if isinstance(token_value, str) else None

    return None


def verify_token_with_auth_service(token: str) -> TokenResponse:
    """Verify JWT token by calling auth-service"""
    try:
        auth_service_url = current_app.config.get("AUTH_SERVICE_URL", "http://localhost:5001")
        verify_url = f"{auth_service_url}/auth/verify-token"

        response = requests.post(verify_url, json={"token": token}, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get("valid"):
                payload = {
                    "sub": data.get("user_id"),
                    "user_id": data.get("user_id"),
                    "username": data.get("username"),
                    "email": data.get("email"),
                    "role": data.get("role", "public"),
                }
                return payload, None
            else:
                logger.warning("Token validation failed", extra={"error": data.get("error")})
                return None, data.get("error", "Invalid token")
        else:
            error_data = (
                response.json()
                if response.headers.get("content-type") == "application/json"
                else {}
            )
            logger.warning("Token verification failed", extra={"status": response.status_code})
            return None, error_data.get("error", "Token verification failed")

    except requests.exceptions.Timeout:
        logger.error("Auth service timeout")
        return None, "Auth service timeout"
    except requests.exceptions.ConnectionError:
        logger.error("Auth service unavailable")
        return None, "Auth service unavailable"
    except Exception as e:
        logger.exception("Token verification error")
        return None, f"Token verification error: {str(e)}"


def token_required(f: Callable) -> Callable:
    """Decorator to require valid JWT token"""

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        token = get_token_from_header()

        if not token:
            return jsonify({"error": "Missing authentication token"}), 401

        payload, error = verify_token_with_auth_service(token)
        if error or not payload:
            return jsonify({"error": error or "Invalid or expired token"}), 401

        # Add user info to kwargs
        kwargs["current_user_id"] = payload.get("sub") or payload.get("user_id")
        kwargs["current_user_role"] = payload.get("role", "public")

        return f(*args, **kwargs)

    return decorated


def admin_required(f: Callable) -> Callable:
    """Decorator to require admin role"""

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        token = get_token_from_header()

        if not token:
            return jsonify({"error": "Missing authentication token"}), 401

        payload, error = verify_token_with_auth_service(token)
        if error or not payload:
            return jsonify({"error": error or "Invalid or expired token"}), 401

        role = payload.get("role", "public")
        if role != "admin":
            return jsonify({"error": "Admin access required"}), 403

        # Add user info to kwargs
        kwargs["current_user_id"] = payload.get("sub") or payload.get("user_id")
        kwargs["current_user_role"] = role

        return f(*args, **kwargs)

    return decorated
