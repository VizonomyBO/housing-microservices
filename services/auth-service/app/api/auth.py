"""
Authentication API endpoints
"""

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, make_response, request

from app import limiter
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utils.security import generate_reset_token

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

ERROR_NO_DATA = "No data provided"
ERROR_UNEXPECTED = "An unexpected error occurred"
ERROR_UNKNOWN = "Unknown error"


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    """
    Register a new user.
    """
    try:
        data = request.get_json()

        if not data:
            logger.warning("Registration attempt with no data")
            return jsonify({"error": ERROR_NO_DATA}), 400

        email = data.get("email")
        username = data.get("username")
        password = data.get("password")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        country_code = data.get("country_code", "USA")
        role = data.get("role", "public")

        missing_fields = []
        if not email:
            missing_fields.append("email")
        if not username:
            missing_fields.append("username")
        if not password:
            missing_fields.append("password")

        if missing_fields:
            error_message = f"Missing required field(s): {', '.join(missing_fields)}"
            logger.warning(
                "Registration attempt with missing required fields",
                extra={
                    "missing_fields": missing_fields,
                    "email_provided": bool(email),
                    "username_provided": bool(username),
                    "password_provided": bool(password),
                },
            )
            return jsonify({"error": error_message}), 400

        logger.info("Attempting to create user", extra={"email": email, "username": username})
        user, error = UserService.create_user(
            email=email,
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            country_code=country_code,
            role=role,
        )

        if error:
            status_code = 409 if "already" in error.lower() else 400
            logger.warning(
                "User creation failed",
                extra={
                    "email": email,
                    "username": username,
                    "error": error,
                    "status_code": status_code,
                },
            )
            return jsonify({"error": error}), status_code

        if user is None:
            logger.error(
                "User creation returned None without error",
                extra={"email": email, "username": username},
            )
            return jsonify({"error": "Failed to create user"}), 500

        logger.info(
            "User registered successfully",
            extra={
                "user_id": user.id,
                "email": email,
                "username": username,
                "country_code": country_code,
                "role": role,
            },
        )
        return jsonify({"message": "User registered successfully", "user": user.to_dict()}), 201

    except Exception:
        logger.exception("Unexpected error during user registration")
        return jsonify({"error": ERROR_UNEXPECTED}), 500


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    """
    Authenticate user and return access and refresh tokens.
    """
    try:
        data = request.get_json()

        if not data:
            logger.warning("Login attempt with no data")
            return jsonify({"error": ERROR_NO_DATA}), 400

        login_identifier = data.get("login")
        password = data.get("password")

        if not login_identifier or not password:
            logger.warning("Login attempt with missing credentials")
            return jsonify({"error": "Login and password are required"}), 400

        # Authenticate user
        logger.info("Authentication attempt", extra={"login_identifier": login_identifier})
        user, error = AuthService.authenticate_user(login_identifier, password)

        if error or user is None:
            logger.warning(
                "Authentication failed",
                extra={
                    "login_identifier": login_identifier,
                    "error": error if error else ERROR_UNKNOWN,
                },
            )
            return jsonify({"error": error if error else "Authentication failed"}), 401

        access_token = AuthService.generate_access_token(user)

        user_agent = request.headers.get("User-Agent")
        ip_address = request.remote_addr

        refresh_token = AuthService.generate_refresh_token(user, user_agent, ip_address)

        UserService.update_last_login(user)

        response = make_response(
            jsonify(
                {
                    "message": "Login successful",
                    "user": user.to_dict(),
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_in": int(
                        current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()
                    ),
                }
            )
        )

        access_token_expires = (
            datetime.now(timezone.utc) + current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
        )
        refresh_token_expires = (
            datetime.now(timezone.utc) + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"]
        )

        cookie_secure = current_app.config.get("COOKIE_SECURE", True)

        response.set_cookie(
            "access_token",
            access_token,
            expires=access_token_expires,
            httponly=True,
            secure=cookie_secure,
            samesite="Lax",
            path="/",
        )

        response.set_cookie(
            "refresh_token",
            refresh_token,
            expires=refresh_token_expires,
            httponly=True,
            secure=cookie_secure,
            samesite="Lax",
            path="/",
        )

        logger.info("Login successful", extra={"user_id": user.id, "username": user.username})
        return response, 200

    except Exception:
        logger.exception("Unexpected error during login")
        return jsonify({"error": ERROR_UNEXPECTED}), 500


@auth_bp.route("/refresh", methods=["POST"])
@limiter.limit("20 per minute")
def refresh():
    """
    Refresh access token using a valid refresh token.
    Supports both cookie-based and JSON body-based refresh tokens.
    """
    try:
        refresh_token = request.cookies.get("refresh_token")

        if not refresh_token:
            data = request.get_json() if request.is_json else {}
            refresh_token = data.get("refresh_token") if data else None

        if not refresh_token:
            logger.warning("Token refresh attempt with missing refresh token")
            return jsonify({"error": "Refresh token is required"}), 400

        logger.info("Attempting to refresh token")
        new_access_token, new_refresh_token, error = AuthService.refresh_access_token(refresh_token)

        if error or new_access_token is None or new_refresh_token is None:
            logger.warning(
                "Token refresh failed", extra={"error": error if error else ERROR_UNKNOWN}
            )
            return jsonify({"error": error if error else "Failed to refresh token"}), 401

        # Create response
        response = make_response(
            jsonify(
                {
                    "message": "Token refreshed successfully",
                    "access_token": new_access_token,
                    "refresh_token": new_refresh_token,
                    "expires_in": int(
                        current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()
                    ),
                }
            )
        )

        access_token_expires = (
            datetime.now(timezone.utc) + current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
        )
        refresh_token_expires = (
            datetime.now(timezone.utc) + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"]
        )

        cookie_secure = current_app.config.get("COOKIE_SECURE", True)

        response.set_cookie(
            "access_token",
            new_access_token,
            expires=access_token_expires,
            httponly=True,
            secure=cookie_secure,
            samesite="Lax",
            path="/",
        )

        response.set_cookie(
            "refresh_token",
            new_refresh_token,
            expires=refresh_token_expires,
            httponly=True,
            secure=cookie_secure,
            samesite="Lax",
            path="/",
        )

        logger.info("Token refreshed successfully")
        return response, 200

    except Exception:
        logger.exception("Unexpected error during token refresh")
        return jsonify({"error": ERROR_UNEXPECTED}), 500


@auth_bp.route("/logout", methods=["POST"])
@limiter.limit("10 per minute")
def logout():
    """
    Logout user by revoking refresh token.
    Supports both cookie-based and JSON body-based refresh tokens.
    """
    try:
        refresh_token = request.cookies.get("refresh_token")

        if not refresh_token:
            data = request.get_json() if request.is_json else {}
            refresh_token = data.get("refresh_token") if data else None

        if not refresh_token:
            logger.warning("Logout attempt with missing refresh token")
            return jsonify({"error": "Refresh token is required"}), 400

        logger.info("Revoking refresh token")
        AuthService.revoke_refresh_token(refresh_token)

        response = make_response(jsonify({"message": "Logout successful"}))

        cookie_secure = current_app.config.get("COOKIE_SECURE", True)

        response.set_cookie(
            "access_token",
            "",
            expires=0,
            httponly=True,
            secure=cookie_secure,
            samesite="Lax",
            path="/",
        )

        response.set_cookie(
            "refresh_token",
            "",
            expires=0,
            httponly=True,
            secure=cookie_secure,
            samesite="Lax",
            path="/",
        )

        logger.info("Logout successful")
        return response, 200

    except Exception:
        logger.exception("Unexpected error during logout")
        return jsonify({"error": ERROR_UNEXPECTED}), 500


@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per hour")
def forgot_password():
    """
    Request password reset token.
    """
    try:
        data = request.get_json()

        if not data:
            logger.warning("Password reset request with no data")
            return jsonify({"error": ERROR_NO_DATA}), 400

        email = data.get("email")

        if not email:
            logger.warning("Password reset request with missing email")
            return jsonify({"error": "Email is required"}), 400

        # Find user by email
        logger.info("Password reset request", extra={"email": email})
        user = UserService.get_user_by_email(email)

        if user:
            reset_token = generate_reset_token()
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

            if UserService.set_reset_token(user, reset_token, expires_at):
                logger.info(
                    "Password reset token generated", extra={"user_id": user.id, "email": email}
                )
                # TODO: Send email with reset token
                # In production, you would send an email like:
                # send_email(
                #     to=user.email,
                #     subject='Password Reset Request',
                #     body=f'Your reset token is: {reset_token}\nExpires in 1 hour.'
                # )

                # For development, log the token (REMOVE IN PRODUCTION)
                logger.debug(f"Password reset token for {email}: {reset_token}")
            else:
                logger.error(
                    "Failed to set reset token", extra={"user_id": user.id, "email": email}
                )

        return jsonify({"message": "If the email exists, a password reset link has been sent"}), 200

    except Exception:
        logger.exception("Unexpected error during password reset request")
        return jsonify({"error": ERROR_UNEXPECTED}), 500


@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("5 per hour")
def reset_password():
    """
    Reset password using a valid reset token.
    """
    try:
        data = request.get_json()

        if not data:
            logger.warning("Password reset attempt with no data")
            return jsonify({"error": ERROR_NO_DATA}), 400

        token = data.get("token")
        new_password = data.get("new_password")

        if not token or not new_password:
            logger.warning("Password reset attempt with missing token or password")
            return jsonify({"error": "Token and new password are required"}), 400

        from app.models.user import User

        logger.info("Attempting password reset with token")
        user = User.query.filter_by(reset_token=token).first()

        if not user:
            logger.warning("Password reset attempt with invalid token")
            return jsonify({"error": "Invalid or expired reset token"}), 400

        if not user.reset_token_expires or datetime.now(timezone.utc) > user.reset_token_expires:
            logger.warning("Password reset attempt with expired token", extra={"user_id": user.id})
            UserService.clear_reset_token(user)
            return jsonify({"error": "Reset token has expired"}), 400

        success, error = UserService.update_password(user, new_password)

        if not success:
            logger.warning("Password update failed", extra={"user_id": user.id, "error": error})
            return jsonify({"error": error}), 400

        UserService.clear_reset_token(user)

        AuthService.revoke_all_user_tokens(user.id)

        logger.info("Password reset successful", extra={"user_id": user.id})
        return (
            jsonify({"message": "Password reset successful. Please login with your new password."}),
            200,
        )

    except Exception:
        logger.exception("Unexpected error during password reset")
        return jsonify({"error": ERROR_UNEXPECTED}), 500


@auth_bp.route("/verify-token", methods=["POST"])
def verify_token():
    """
    Verify if an access token is valid.
    Supports token from Authorization header, cookies, or JSON body.
    """
    try:
        token = None

        # Try Authorization header first
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]

        # Fallback to cookie
        if not token:
            token = request.cookies.get("access_token")

        # Fallback to request body
        if not token:
            data = request.get_json() if request.is_json else {}
            if data:
                token = data.get("token") or data.get("access_token")

        if not token:
            logger.warning("Token verification attempt with no token")
            return jsonify({"error": "Token is required"}), 400

        logger.info("Attempting to verify token")
        payload, error = AuthService.verify_access_token(token)

        if error or payload is None:
            logger.warning(
                "Token verification failed", extra={"error": error if error else ERROR_UNKNOWN}
            )
            return jsonify({"valid": False, "error": error if error else "Invalid token"}), 401

        logger.info("Token verified successfully", extra={"user_id": payload.get("user_id")})
        return (
            jsonify(
                {
                    "valid": True,
                    "user_id": payload.get("user_id"),
                    "username": payload.get("username"),
                    "email": payload.get("email"),
                    "role": payload.get("role"),
                }
            ),
            200,
        )

    except Exception:
        logger.exception("Unexpected error during token verification")
        return jsonify({"error": ERROR_UNEXPECTED}), 500
