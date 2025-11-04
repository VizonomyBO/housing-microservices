"""
Authentication decorators for protecting endpoints
"""

from functools import wraps

from flask import current_app, jsonify, request

from app.services.auth_service import AuthService


def require_auth(f):
    """
    Decorator to require authentication via JWT token.
    Returns the user object and token payload if authenticated.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization header with Bearer token is required"}), 401

        token = auth_header.split(" ")[1]

        # Verify token
        payload, error = AuthService.verify_access_token(token)
        if error or payload is None:
            return jsonify({"error": error if error else "Invalid token"}), 401

        # Get user from token
        from app.models.user import User

        user_id = payload.get("user_id")
        user = User.query.get(user_id)

        if not user:
            return jsonify({"error": "User not found"}), 401

        if user.status != "active":
            return jsonify({"error": f"User account is {user.status}"}), 403

        # Add user to kwargs for the route function
        kwargs["current_user"] = user
        kwargs["token_payload"] = payload

        return f(*args, **kwargs)

    return decorated_function


def require_admin(f):
    """
    Decorator to require admin role.
    Must be used after @require_auth
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = kwargs.get("current_user")

        if not current_user:
            return jsonify({"error": "Authentication required"}), 401

        if current_user.role != "admin":
            return jsonify({"error": "Admin access required"}), 403

        return f(*args, **kwargs)

    return decorated_function

