"""
Authentication API endpoints
"""

from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request

from app import limiter
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utils.auth_decorators import require_auth
from app.utils.security import generate_reset_token

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    """
    Register a new user.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Extract fields
    email = data.get("email")
    password = data.get("password")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    country_code = data.get("country_code", "USA")
    role = data.get("role", "public")

    # Validate required fields
    if not email or not password or not first_name or not last_name:
        return jsonify({"error": "Email, password, first_name, and last_name are required"}), 400

    # Create user
    user, error = UserService.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        country_code=country_code,
        role=role,
    )

    if error:
        status_code = 409 if "already" in error.lower() else 400
        return jsonify({"error": error}), status_code

    if user is None:
        return jsonify({"error": "Failed to create user"}), 500

    return jsonify({"message": "User registered successfully", "user": user.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    """
    Authenticate user and return access and refresh tokens.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    login_identifier = data.get("login")
    password = data.get("password")

    if not login_identifier or not password:
        return jsonify({"error": "Login and password are required"}), 400

    # Authenticate user
    user, error = AuthService.authenticate_user(login_identifier, password)

    if error or user is None:
        return jsonify({"error": error if error else "Authentication failed"}), 401

    # Generate tokens
    access_token = AuthService.generate_access_token(user)

    # Get user agent and IP for refresh token tracking
    user_agent = request.headers.get("User-Agent")
    ip_address = request.remote_addr

    refresh_token = AuthService.generate_refresh_token(user, user_agent, ip_address)

    # Update last login
    UserService.update_last_login(user)

    return (
        jsonify(
            {
                "message": "Login successful",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()),
                "user": user.to_dict(),
            }
        ),
        200,
    )


@auth_bp.route("/refresh", methods=["POST"])
@limiter.limit("20 per minute")
def refresh():
    """
    Refresh access token using a valid refresh token.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    refresh_token = data.get("refresh_token")

    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400

    # Refresh tokens
    new_access_token, new_refresh_token, error = AuthService.refresh_access_token(refresh_token)

    if error or new_access_token is None or new_refresh_token is None:
        return jsonify({"error": error if error else "Failed to refresh token"}), 401

    return (
        jsonify(
            {
                "message": "Token refreshed successfully",
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "Bearer",
                "expires_in": int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()),
            }
        ),
        200,
    )


@auth_bp.route("/logout", methods=["POST"])
@limiter.limit("10 per minute")
def logout():
    """
    Logout user by revoking refresh token.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    refresh_token = data.get("refresh_token")

    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400

    # Revoke token
    AuthService.revoke_refresh_token(refresh_token)

    return jsonify({"message": "Logout successful"}), 200


@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per hour")
def forgot_password():
    """
    Request password reset token.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    email = data.get("email")

    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Find user by email
    user = UserService.get_user_by_email(email)

    # Always return success to prevent email enumeration
    # In production, send actual email here
    if user:
        # Generate reset token
        reset_token = generate_reset_token()
        expires_at = datetime.utcnow() + timedelta(hours=1)

        # Store reset token
        UserService.set_reset_token(user, reset_token, expires_at)

        # TODO: Send email with reset token
        # In production, you would send an email like:
        # send_email(
        #     to=user.email,
        #     subject='Password Reset Request',
        #     body=f'Your reset token is: {reset_token}\nExpires in 1 hour.'
        # )

        # For development, log the token (REMOVE IN PRODUCTION)
        print(f"Password reset token for {email}: {reset_token}")

    return jsonify({"message": "If the email exists, a password reset link has been sent"}), 200


@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("5 per hour")
def reset_password():
    """
    Reset password using a valid reset token.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    token = data.get("token")
    new_password = data.get("new_password")

    if not token or not new_password:
        return jsonify({"error": "Token and new password are required"}), 400

    # Find user with valid reset token
    from app.models.user import User

    user = User.query.filter_by(reset_token=token).first()

    if not user:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    # Check if token is expired
    if not user.reset_token_expires or datetime.utcnow() > user.reset_token_expires:
        UserService.clear_reset_token(user)
        return jsonify({"error": "Reset token has expired"}), 400

    # Update password
    success, error = UserService.update_password(user, new_password)

    if not success:
        return jsonify({"error": error}), 400

    # Clear reset token
    UserService.clear_reset_token(user)

    # Revoke all existing refresh tokens for security
    AuthService.revoke_all_user_tokens(user.user_id)

    return (
        jsonify({"message": "Password reset successful. Please login with your new password."}),
        200,
    )


@auth_bp.route("/verify-token", methods=["POST"])
def verify_token():
    """
    Verify if an access token is valid.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    token = data.get("token")

    if not token:
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            return jsonify({"error": "Token is required"}), 400

    # Verify token
    payload, error = AuthService.verify_access_token(token)

    if error or payload is None:
        return jsonify({"valid": False, "error": error if error else "Invalid token"}), 401

    return (
        jsonify(
            {
                "valid": True,
                "user_id": payload.get("user_id"),
                "email": payload.get("email"),
            }
        ),
        200,
    )


@auth_bp.route("/me", methods=["GET"])
@require_auth
@limiter.limit("30 per minute")
def get_current_user(current_user, token_payload):
    """
    Get the current authenticated user's information.
    Requires Bearer token in Authorization header.
    """
    return jsonify(current_user.to_dict()), 200
