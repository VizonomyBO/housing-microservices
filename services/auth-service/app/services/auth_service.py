"""
Authentication service layer for JWT token management
"""

import logging
import secrets
from datetime import datetime
from typing import cast

import jwt
from flask import current_app
from sqlalchemy import BigInteger
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.security import verify_password

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication and token management"""

    @staticmethod
    def _check_user_status(user: User, login: str) -> tuple[None, str] | None:
        """
        Check if user status allows authentication.

        Args:
            user: User object to check
            login: Login identifier for logging

        Returns:
            Tuple of (None, error_message) if status is invalid, None if status is valid
        """
        status_messages = {
            "pending": "Account is pending activation. Please verify your email or contact support.",
            "suspended": "Account has been suspended. Please contact support.",
            "inactive": "Account is inactive. Please contact support.",
        }

        if user.status in status_messages:
            logger.warning(
                f"Authentication failed: account {user.status}",
                extra={"user_id": user.user_id, "login": login, "status": user.status},
            )
            return None, status_messages[user.status]

        if user.status != "active":
            logger.warning(
                "Authentication failed: invalid account status",
                extra={"user_id": user.user_id, "login": login, "status": user.status},
            )
            return None, f"Account status is {user.status}. Please contact support."

        return None

    @staticmethod
    def _find_user_by_login(login: str) -> User | None:
        """
        Find user by email or username.

        Args:
            login: Email address or username

        Returns:
            User object if found, None otherwise
        """
        # Try email first
        user = cast(User | None, User.query.filter(User.email == login).first())

        # If not found by email, try username (email prefix)
        if not user:
            user = cast(User | None, User.query.filter(User.email.like(f"{login}@%")).first())

        return user

    @staticmethod
    def authenticate_user(login: str, password: str) -> tuple[User, None] | tuple[None, str]:
        """
        Authenticate user with email and password.

        Args:
            login: Email address
            password: Plain text password

        Returns:
            Tuple of (User, None) on success or (None, error_message) on failure
        """
        try:
            logger.info("Authentication attempt", extra={"login": login})

            # Find user by email or username
            user = AuthService._find_user_by_login(login)

            if not user:
                logger.warning("Authentication failed: user not found", extra={"login": login})
                return None, "Invalid credentials"

            # Check user status
            status_error = AuthService._check_user_status(user, login)
            if status_error:
                return status_error

            # Verify password
            if not verify_password(user.password_hash, password):
                logger.warning(
                    "Authentication failed: invalid password",
                    extra={"user_id": user.user_id, "login": login},
                )
                return None, "Invalid credentials"

            logger.info(
                "Authentication successful",
                extra={"user_id": user.user_id, "login": login, "email": user.email},
            )
            return user, None
        except SQLAlchemyError as e:
            logger.exception(
                "Database error during authentication", extra={"login": login, "error": str(e)}
            )
            raise
        except Exception as e:
            logger.exception(
                "Unexpected error during authentication", extra={"login": login, "error": str(e)}
            )
            raise

    @staticmethod
    def generate_access_token(user: User) -> str:
        """Generate JWT access token"""
        try:
            logger.debug(
                "Generating access token", extra={"user_id": user.user_id, "email": user.email}
            )

            payload = {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "exp": datetime.utcnow() + current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
                "iat": datetime.utcnow(),
                "type": "access",
            }

            encoded = jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")
            # jwt.encode can return str or bytes depending on version
            token = encoded if isinstance(encoded, str) else encoded.decode("utf-8")

            logger.debug(
                "Access token generated successfully",
                extra={"user_id": user.user_id, "email": user.email},
            )
            return token
        except Exception as e:
            logger.exception(
                "Failed to generate access token",
                extra={"user_id": user.user_id, "email": user.email, "error": str(e)},
            )
            raise

    @staticmethod
    def generate_refresh_token(
        user: User, user_agent: str | None = None, ip_address: str | None = None
    ) -> str:
        """Generate and store refresh token"""
        try:
            logger.debug(
                "Generating refresh token",
                extra={"user_id": user.user_id, "email": user.email, "ip_address": ip_address},
            )

            payload = {
                "user_id": user.user_id,
                "exp": datetime.utcnow() + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"],
                "iat": datetime.utcnow(),
                "type": "refresh",
                "jti": secrets.token_urlsafe(16),  # Unique token ID to prevent duplicates
            }

            encoded = jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")
            # jwt.encode can return str or bytes depending on version
            token = encoded if isinstance(encoded, str) else encoded.decode("utf-8")

            # Store refresh token in database
            refresh_token = RefreshToken(
                user_id=user.user_id,
                token=token,
                expires_at=datetime.utcnow() + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"],
                user_agent=user_agent[:500] if user_agent else None,
                ip_address=ip_address,
            )

            db.session.add(refresh_token)
            db.session.commit()

            logger.info(
                "Refresh token generated and stored successfully",
                extra={
                    "user_id": user.user_id,
                    "email": user.email,
                    "ip_address": ip_address,
                    "token_id": refresh_token.id if hasattr(refresh_token, "id") else None,
                },
            )
            return token
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.exception(
                "Database error while generating refresh token",
                extra={
                    "user_id": user.user_id,
                    "email": user.email,
                    "ip_address": ip_address,
                    "error": str(e),
                },
            )
            raise
        except Exception as e:
            db.session.rollback()
            logger.exception(
                "Failed to generate refresh token",
                extra={
                    "user_id": user.user_id,
                    "email": user.email,
                    "ip_address": ip_address,
                    "error": str(e),
                },
            )
            raise

    @staticmethod
    def verify_access_token(token: str) -> tuple[dict[str, object], None] | tuple[None, str]:
        """
        Verify and decode access token.

        Returns:
            Tuple of (payload, None) on success or (None, error_message) on failure
        """
        try:
            logger.debug("Verifying access token")
            payload = jwt.decode(token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])

            if payload.get("type") != "access":
                logger.warning(
                    "Access token verification failed: invalid token type",
                    extra={"user_id": payload.get("user_id"), "token_type": payload.get("type")},
                )
                return None, "Invalid token type"

            logger.debug(
                "Access token verified successfully",
                extra={"user_id": payload.get("user_id"), "email": payload.get("email")},
            )
            return payload, None
        except jwt.ExpiredSignatureError:
            logger.warning("Access token verification failed: token expired")
            return None, "Token has expired"
        except jwt.InvalidTokenError as e:
            logger.warning(
                "Access token verification failed: invalid token", extra={"error": str(e)}
            )
            return None, "Invalid token"
        except Exception as e:
            logger.exception(
                "Unexpected error during access token verification", extra={"error": str(e)}
            )
            return None, "Token verification failed"

    @staticmethod
    def verify_refresh_token(token: str) -> tuple[RefreshToken, None] | tuple[None, str]:
        """
        Verify refresh token and check if it's valid in database.

        Returns:
            Tuple of (RefreshToken, None) on success or (None, error_message) on failure
        """
        try:
            logger.debug("Verifying refresh token")
            # Decode token
            payload = jwt.decode(token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])

            if payload.get("type") != "refresh":
                logger.warning(
                    "Refresh token verification failed: invalid token type",
                    extra={"user_id": payload.get("user_id"), "token_type": payload.get("type")},
                )
                return None, "Invalid token type"

            # Check if token exists and is valid in database
            refresh_token = RefreshToken.query.filter_by(token=token).first()

            if not refresh_token:
                logger.warning(
                    "Refresh token verification failed: token not found in database",
                    extra={"user_id": payload.get("user_id")},
                )
                return None, "Token not found"

            if not refresh_token.is_valid():
                logger.warning(
                    "Refresh token verification failed: token invalid or expired",
                    extra={
                        "user_id": refresh_token.user_id,
                        "token_id": refresh_token.id if hasattr(refresh_token, "id") else None,
                        "is_revoked": (
                            refresh_token.is_revoked
                            if hasattr(refresh_token, "is_revoked")
                            else None
                        ),
                    },
                )
                return None, "Token is invalid or expired"

            logger.debug(
                "Refresh token verified successfully",
                extra={
                    "user_id": refresh_token.user_id,
                    "token_id": refresh_token.id if hasattr(refresh_token, "id") else None,
                },
            )
            return refresh_token, None
        except jwt.ExpiredSignatureError:
            logger.warning("Refresh token verification failed: token expired")
            return None, "Token has expired"
        except jwt.InvalidTokenError as e:
            logger.warning(
                "Refresh token verification failed: invalid token", extra={"error": str(e)}
            )
            return None, "Invalid token"
        except SQLAlchemyError as e:
            logger.exception(
                "Database error during refresh token verification", extra={"error": str(e)}
            )
            raise
        except Exception as e:
            logger.exception(
                "Unexpected error during refresh token verification", extra={"error": str(e)}
            )
            return None, "Token verification failed"

    @staticmethod
    def refresh_access_token(refresh_token: str) -> tuple[str, str, None] | tuple[None, None, str]:
        """
        Generate new access token and rotate refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token, None) on success or (None, None, error) on failure
        """
        try:
            logger.info("Attempting to refresh access token")

            # Verify refresh token
            token_obj, error = AuthService.verify_refresh_token(refresh_token)
            if error or token_obj is None:
                logger.warning(
                    "Token refresh failed: invalid refresh token",
                    extra={"error": error if error else "Invalid refresh token"},
                )
                return None, None, error if error else "Invalid refresh token"

            # Get user
            user = User.query.get(token_obj.user_id)
            if not user:
                logger.warning(
                    "Token refresh failed: user not found", extra={"user_id": token_obj.user_id}
                )
                return None, None, "User not found or inactive"

            if user.status != "active":
                logger.warning(
                    "Token refresh failed: user not active",
                    extra={"user_id": user.user_id, "status": user.status},
                )
                return None, None, "User not found or inactive"

            # Revoke old refresh token
            try:
                token_obj.revoke()
                db.session.commit()
                logger.debug(
                    "Old refresh token revoked",
                    extra={
                        "user_id": user.user_id,
                        "token_id": token_obj.id if hasattr(token_obj, "id") else None,
                    },
                )
            except SQLAlchemyError as e:
                db.session.rollback()
                logger.exception(
                    "Database error while revoking old refresh token",
                    extra={"user_id": user.user_id, "error": str(e)},
                )
                raise

            # Generate new tokens
            new_access_token = AuthService.generate_access_token(user)
            new_refresh_token = AuthService.generate_refresh_token(
                user, token_obj.user_agent, token_obj.ip_address
            )

            logger.info(
                "Token refresh successful",
                extra={
                    "user_id": user.user_id,
                    "email": user.email,
                    "ip_address": token_obj.ip_address,
                },
            )
            return new_access_token, new_refresh_token, None
        except SQLAlchemyError as e:
            logger.exception("Database error during token refresh", extra={"error": str(e)})
            raise
        except Exception as e:
            logger.exception("Unexpected error during token refresh", extra={"error": str(e)})
            return None, None, "Token refresh failed"

    @staticmethod
    def revoke_refresh_token(token: str) -> bool:
        """Revoke a refresh token"""
        try:
            logger.info("Attempting to revoke refresh token")
            refresh_token = RefreshToken.query.filter_by(token=token).first()
            if refresh_token:
                refresh_token.revoke()
                db.session.commit()
                logger.info(
                    "Refresh token revoked successfully",
                    extra={
                        "user_id": refresh_token.user_id,
                        "token_id": refresh_token.id if hasattr(refresh_token, "id") else None,
                    },
                )
            else:
                logger.warning("Refresh token not found for revocation")
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.exception("Database error while revoking refresh token", extra={"error": str(e)})
            raise
        except Exception as e:
            db.session.rollback()
            logger.exception(
                "Unexpected error while revoking refresh token", extra={"error": str(e)}
            )
            return False

    @staticmethod
    def revoke_all_user_tokens(user_id: int | BigInteger) -> bool:
        """Revoke all refresh tokens for a user"""
        try:
            logger.info("Attempting to revoke all tokens for user", extra={"user_id": user_id})

            result = RefreshToken.query.filter_by(user_id=user_id, is_revoked=False).update(
                {"is_revoked": True}
            )
            db.session.commit()

            logger.info(
                "All user tokens revoked successfully",
                extra={"user_id": user_id, "tokens_revoked": result},
            )
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.exception(
                "Database error while revoking all user tokens",
                extra={"user_id": user_id, "error": str(e)},
            )
            raise
        except Exception as e:
            db.session.rollback()
            logger.exception(
                "Unexpected error while revoking all user tokens",
                extra={"user_id": user_id, "error": str(e)},
            )
            return False

    @staticmethod
    def cleanup_expired_tokens() -> int:
        """Remove expired tokens from database"""
        try:
            logger.info("Starting cleanup of expired tokens")

            count_result = RefreshToken.query.filter(
                RefreshToken.expires_at < datetime.utcnow()
            ).delete()
            db.session.commit()

            count = int(count_result) if count_result is not None else 0
            logger.info("Expired tokens cleanup completed", extra={"tokens_deleted": count})
            return count
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.exception(
                "Database error during expired tokens cleanup", extra={"error": str(e)}
            )
            raise
        except Exception as e:
            db.session.rollback()
            logger.exception(
                "Unexpected error during expired tokens cleanup", extra={"error": str(e)}
            )
            return 0
