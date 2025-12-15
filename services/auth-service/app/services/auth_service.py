"""
Authentication service layer for JWT token management
"""

import logging
import os
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import jwt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.security import verify_password

if TYPE_CHECKING:
    from app.config import Config

logger = logging.getLogger(__name__)


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


def _get_jwt_access_token_expires(config: "Config | None" = None):
    """Get JWT access token expiration from config"""
    if config:
        return config.JWT_ACCESS_TOKEN_EXPIRES
    # Try Flask context (for backward compatibility)
    try:
        from flask import current_app

        return current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    except RuntimeError:
        from datetime import timedelta

        # Default to 15 minutes
        return timedelta(minutes=15)


def _get_jwt_refresh_token_expires(config: "Config | None" = None):
    """Get JWT refresh token expiration from config"""
    if config:
        return config.JWT_REFRESH_TOKEN_EXPIRES
    # Try Flask context (for backward compatibility)
    try:
        from flask import current_app

        return current_app.config["JWT_REFRESH_TOKEN_EXPIRES"]
    except RuntimeError:
        from datetime import timedelta

        # Default to 30 days
        return timedelta(days=30)


class AuthService:
    """Service for authentication and token management"""

    @staticmethod
    def authenticate_user(
        session: Session, login: str, password: str
    ) -> tuple[User, None] | tuple[None, str]:
        """
        Authenticate user with email and password.

        Args:
            session: Database session
            login: Email address
            password: Plain text password

        Returns:
            Tuple of (User, None) on success or (None, error_message) on failure
        """
        try:
            logger.info("Authentication attempt", extra={"login": login})

            # Find user by email or username
            # Try email first
            user = session.query(User).filter(User.email == login).first()

            # If not found by email, try username (email prefix)
            if not user:
                user = session.query(User).filter(User.email.like(f"{login}@%")).first()

            if not user:
                logger.warning("Authentication failed: user not found", extra={"login": login})
                return None, "Invalid credentials"

            # Check user status
            if user.status == "pending":
                logger.warning(
                    "Authentication failed: account pending activation",
                    extra={"user_id": str(user.user_id), "login": login, "status": user.status},
                )
                return (
                    None,
                    "Account is pending activation. Please verify your email or contact support.",
                )
            if user.status == "suspended":
                logger.warning(
                    "Authentication failed: account suspended",
                    extra={"user_id": str(user.user_id), "login": login, "status": user.status},
                )
                return None, "Account has been suspended. Please contact support."
            if user.status == "inactive":
                logger.warning(
                    "Authentication failed: account inactive",
                    extra={"user_id": str(user.user_id), "login": login, "status": user.status},
                )
                return None, "Account is inactive. Please contact support."
            if user.status != "active":
                logger.warning(
                    "Authentication failed: invalid account status",
                    extra={"user_id": str(user.user_id), "login": login, "status": user.status},
                )
                return None, f"Account status is {user.status}. Please contact support."

            # Verify password
            # Extract password_hash value (SQLAlchemy Column[str] returns str at runtime)
            password_hash: str = user.password_hash  # type: ignore[assignment]
            if not verify_password(password_hash, password):
                logger.warning(
                    "Authentication failed: invalid password",
                    extra={"user_id": str(user.user_id), "login": login},
                )
                return None, "Invalid credentials"

            logger.info(
                "Authentication successful",
                extra={"user_id": str(user.user_id), "login": login, "email": user.email},
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
    def generate_access_token(user: User, config: "Config | None" = None) -> str:
        """Generate JWT access token"""
        try:
            user_id_str = str(user.user_id)
            logger.debug(
                "Generating access token", extra={"user_id": user_id_str, "email": user.email}
            )

            expires = _get_jwt_access_token_expires(config)
            secret_key = _get_jwt_secret_key(config)

            payload = {
                "user_id": user_id_str,
                "username": user.username,
                "email": user.email,
                "exp": datetime.now(UTC) + expires,
                "iat": datetime.now(UTC),
                "type": "access",
            }

            encoded = jwt.encode(payload, secret_key, algorithm="HS256")
            # jwt.encode can return str or bytes depending on version
            token = encoded if isinstance(encoded, str) else encoded.decode("utf-8")

            logger.debug(
                "Access token generated successfully",
                extra={"user_id": user_id_str, "email": user.email},
            )
            return token
        except Exception as e:
            logger.exception(
                "Failed to generate access token",
                extra={"user_id": user_id_str, "email": user.email, "error": str(e)},
            )
            raise

    @staticmethod
    def generate_refresh_token(
        session: Session,
        user: User,
        user_agent: str | None = None,
        ip_address: str | None = None,
        config: "Config | None" = None,
    ) -> str:
        """Generate and store refresh token"""
        try:
            user_id_str = str(user.user_id)
            logger.debug(
                "Generating refresh token",
                extra={"user_id": user_id_str, "email": user.email, "ip_address": ip_address},
            )

            expires = _get_jwt_refresh_token_expires(config)
            secret_key = _get_jwt_secret_key(config)

            payload = {
                "user_id": user_id_str,
                "exp": datetime.now(UTC) + expires,
                "iat": datetime.now(UTC),
                "type": "refresh",
                "jti": secrets.token_urlsafe(16),  # Unique token ID to prevent duplicates
            }

            encoded = jwt.encode(payload, secret_key, algorithm="HS256")
            # jwt.encode can return str or bytes depending on version
            token = encoded if isinstance(encoded, str) else encoded.decode("utf-8")

            # Store refresh token in database
            refresh_token = RefreshToken(
                user_id=user.user_id,
                token=token,
                expires_at=datetime.now(UTC) + expires,
                user_agent=user_agent[:500] if user_agent else None,
                ip_address=ip_address,
            )

            session.add(refresh_token)
            session.commit()

            logger.info(
                "Refresh token generated and stored successfully",
                extra={
                    "user_id": user_id_str,
                    "email": user.email,
                    "ip_address": ip_address,
                    "token_id": refresh_token.id if hasattr(refresh_token, "id") else None,
                },
            )
            return token
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception(
                "Database error while generating refresh token",
                extra={
                    "user_id": user_id_str,
                    "email": user.email,
                    "ip_address": ip_address,
                    "error": str(e),
                },
            )
            raise
        except Exception as e:
            session.rollback()
            logger.exception(
                "Failed to generate refresh token",
                extra={
                    "user_id": user_id_str,
                    "email": user.email,
                    "ip_address": ip_address,
                    "error": str(e),
                },
            )
            raise

    @staticmethod
    def verify_access_token(
        session: Session, token: str, config: "Config | None" = None
    ) -> tuple[dict[str, object], None] | tuple[None, str]:
        """
        Verify and decode access token.
        Enriches payload with user data from database (country_code, role).

        Returns:
            Tuple of (payload, None) on success or (None, error_message) on failure
        """
        try:
            logger.debug("Verifying access token")
            secret_key = _get_jwt_secret_key(config)
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])

            if payload.get("type") != "access":
                logger.warning(
                    "Access token verification failed: invalid token type",
                    extra={"user_id": payload.get("user_id"), "token_type": payload.get("type")},
                )
                return None, "Invalid token type"

            # Enrich payload with current user data from database
            user_id = payload.get("user_id")
            if user_id:
                try:
                    user_uuid = UUID(str(user_id))
                except ValueError:
                    logger.error(
                        "Invalid user_id in token payload",
                        extra={"user_id": user_id},
                    )
                    return None, "Invalid token payload"

                user = session.get(User, user_uuid)
                if user:
                    # Add country_code and ensure role is current
                    payload["country_code"] = user.country_code
                    payload["role"] = user.role
                    # Ensure roles is a list for middleware compatibility
                    payload["roles"] = [user.role] if user.role else []
                else:
                    logger.warning(
                        "User not found for token",
                        extra={"user_id": user_id},
                    )
                    # Continue with token payload even if user not found (token is still valid)

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
    def verify_refresh_token(
        session: Session, token: str, config: "Config | None" = None
    ) -> tuple[RefreshToken, None] | tuple[None, str]:
        """
        Verify refresh token and check if it's valid in database.

        Returns:
            Tuple of (RefreshToken, None) on success or (None, error_message) on failure
        """
        try:
            logger.debug("Verifying refresh token")
            # Decode token
            secret_key = _get_jwt_secret_key(config)
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])

            if payload.get("type") != "refresh":
                logger.warning(
                    "Refresh token verification failed: invalid token type",
                    extra={"user_id": payload.get("user_id"), "token_type": payload.get("type")},
                )
                return None, "Invalid token type"

            # Check if token exists and is valid in database
            refresh_token = session.query(RefreshToken).filter_by(token=token).first()

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
    def refresh_access_token(
        session: Session, refresh_token: str, config: "Config | None" = None
    ) -> tuple[str, str, None] | tuple[None, None, str]:
        """
        Generate new access token and rotate refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token, None) on success or (None, None, error) on failure
        """
        try:
            logger.info("Attempting to refresh access token")

            # Verify refresh token
            token_obj, error = AuthService.verify_refresh_token(session, refresh_token, config)
            if error or token_obj is None:
                logger.warning(
                    "Token refresh failed: invalid refresh token",
                    extra={"error": error if error else "Invalid refresh token"},
                )
                return None, None, error if error else "Invalid refresh token"

            # Get user
            user: User | None = session.get(User, token_obj.user_id)
            if not user:
                logger.warning(
                    "Token refresh failed: user not found",
                    extra={"user_id": str(token_obj.user_id)},
                )
                return None, None, "User not found or inactive"

            if user.status != "active":
                logger.warning(
                    "Token refresh failed: user not active",
                    extra={"user_id": str(user.user_id), "status": user.status},
                )
                return None, None, "User not found or inactive"

            # Revoke old refresh token
            try:
                token_obj.revoke()
                session.commit()
                logger.debug(
                    "Old refresh token revoked",
                    extra={
                        "user_id": str(user.user_id),
                        "token_id": token_obj.id if hasattr(token_obj, "id") else None,
                    },
                )
            except SQLAlchemyError as e:
                session.rollback()
                logger.exception(
                    "Database error while revoking old refresh token",
                    extra={"user_id": str(user.user_id), "error": str(e)},
                )
                raise

            # Generate new tokens
            new_access_token = AuthService.generate_access_token(user, config)
            # Extract values from token_obj (SQLAlchemy Column types return actual values at runtime)
            user_agent_val = token_obj.user_agent
            ip_address_val = token_obj.ip_address
            user_agent: str | None = str(user_agent_val) if user_agent_val is not None else None
            ip_address: str | None = str(ip_address_val) if ip_address_val is not None else None
            new_refresh_token = AuthService.generate_refresh_token(
                session, user, user_agent, ip_address, config
            )

            logger.info(
                "Token refresh successful",
                extra={
                    "user_id": str(user.user_id),
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
    def revoke_refresh_token(session: Session, token: str) -> bool:
        """Revoke a refresh token"""
        try:
            logger.info("Attempting to revoke refresh token")
            refresh_token = session.query(RefreshToken).filter_by(token=token).first()
            if refresh_token:
                refresh_token.revoke()
                session.commit()
                logger.info(
                    "Refresh token revoked successfully",
                    extra={
                        "user_id": str(refresh_token.user_id),
                        "token_id": refresh_token.id if hasattr(refresh_token, "id") else None,
                    },
                )
            else:
                logger.warning("Refresh token not found for revocation")
            return True
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception("Database error while revoking refresh token", extra={"error": str(e)})
            raise
        except Exception as e:
            session.rollback()
            logger.exception(
                "Unexpected error while revoking refresh token", extra={"error": str(e)}
            )
            return False

    @staticmethod
    def revoke_all_user_tokens(session: Session, user_id: UUID | str) -> bool:
        """Revoke all refresh tokens for a user"""
        try:
            user_uuid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
        except ValueError as exc:
            logger.error("Invalid user_id provided for revocation", extra={"user_id": user_id})
            raise ValueError("user_id must be a valid UUID") from exc

        try:
            logger.info(
                "Attempting to revoke all tokens for user", extra={"user_id": str(user_uuid)}
            )

            result = (
                session.query(RefreshToken)
                .filter_by(user_id=user_uuid, is_revoked=False)
                .update({"is_revoked": True})
            )
            session.commit()

            logger.info(
                "All user tokens revoked successfully",
                extra={"user_id": str(user_uuid), "tokens_revoked": result},
            )
            return True
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception(
                "Database error while revoking all user tokens",
                extra={"user_id": str(user_uuid), "error": str(e)},
            )
            raise
        except Exception as e:
            session.rollback()
            logger.exception(
                "Unexpected error while revoking all user tokens",
                extra={"user_id": str(user_uuid), "error": str(e)},
            )
            return False

    @staticmethod
    def cleanup_expired_tokens(session: Session) -> int:
        """Remove expired tokens from database"""
        try:
            logger.info("Starting cleanup of expired tokens")

            count_result = (
                session.query(RefreshToken)
                .filter(RefreshToken.expires_at < datetime.now(UTC))
                .delete()
            )
            session.commit()

            count = int(count_result) if count_result is not None else 0
            logger.info("Expired tokens cleanup completed", extra={"tokens_deleted": count})
            return count
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception(
                "Database error during expired tokens cleanup", extra={"error": str(e)}
            )
            raise
        except Exception as e:
            session.rollback()
            logger.exception(
                "Unexpected error during expired tokens cleanup", extra={"error": str(e)}
            )
            return 0
