"""
Authentication service layer for JWT token management
"""

from datetime import datetime

import jwt
from flask import current_app
from sqlalchemy import BigInteger

from app import db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.security import verify_password


class AuthService:
    """Service for authentication and token management"""

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
        # Find user by email
        user = User.query.filter(User.email == login).first()

        if not user:
            return None, "Invalid credentials"

        # Check user status
        if user.status == 'pending':
            return None, "Account is pending activation. Please verify your email or contact support."
        if user.status == 'suspended':
            return None, "Account has been suspended. Please contact support."
        if user.status == 'inactive':
            return None, "Account is inactive. Please contact support."
        if user.status != 'active':
            return None, f"Account status is {user.status}. Please contact support."

        # Verify password
        if not verify_password(user.password_hash, password):
            return None, "Invalid credentials"

        return user, None

    @staticmethod
    def generate_access_token(user: User) -> str:
        """Generate JWT access token"""
        payload = {
            "user_id": user.user_id,
            "email": user.email,
            "exp": datetime.utcnow() + current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
            "iat": datetime.utcnow(),
            "type": "access",
        }

        encoded = jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")
        # jwt.encode can return str or bytes depending on version
        return encoded if isinstance(encoded, str) else encoded.decode("utf-8")

    @staticmethod
    def generate_refresh_token(
        user: User, user_agent: str | None = None, ip_address: str | None = None
    ) -> str:
        """Generate and store refresh token"""
        payload = {
            "user_id": user.user_id,
            "exp": datetime.utcnow() + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"],
            "iat": datetime.utcnow(),
            "type": "refresh",
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

        return token

    @staticmethod
    def verify_access_token(token: str) -> tuple[dict[str, object], None] | tuple[None, str]:
        """
        Verify and decode access token.

        Returns:
            Tuple of (payload, None) on success or (None, error_message) on failure
        """
        try:
            payload = jwt.decode(token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])

            if payload.get("type") != "access":
                return None, "Invalid token type"

            return payload, None
        except jwt.ExpiredSignatureError:
            return None, "Token has expired"
        except jwt.InvalidTokenError:
            return None, "Invalid token"

    @staticmethod
    def verify_refresh_token(token: str) -> tuple[RefreshToken, None] | tuple[None, str]:
        """
        Verify refresh token and check if it's valid in database.

        Returns:
            Tuple of (RefreshToken, None) on success or (None, error_message) on failure
        """
        try:
            # Decode token
            payload = jwt.decode(token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])

            if payload.get("type") != "refresh":
                return None, "Invalid token type"

            # Check if token exists and is valid in database
            refresh_token = RefreshToken.query.filter_by(token=token).first()

            if not refresh_token:
                return None, "Token not found"

            if not refresh_token.is_valid():
                return None, "Token is invalid or expired"

            return refresh_token, None
        except jwt.ExpiredSignatureError:
            return None, "Token has expired"
        except jwt.InvalidTokenError:
            return None, "Invalid token"

    @staticmethod
    def refresh_access_token(refresh_token: str) -> tuple[str, str, None] | tuple[None, None, str]:
        """
        Generate new access token and rotate refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token, None) on success or (None, None, error) on failure
        """
        # Verify refresh token
        token_obj, error = AuthService.verify_refresh_token(refresh_token)
        if error or token_obj is None:
            return None, None, error if error else "Invalid refresh token"

        # Get user
        user = User.query.get(token_obj.user_id)
        if not user or user.status != 'active':
            return None, None, "User not found or inactive"

        # Revoke old refresh token
        token_obj.revoke()
        db.session.commit()

        # Generate new tokens
        new_access_token = AuthService.generate_access_token(user)
        new_refresh_token = AuthService.generate_refresh_token(
            user, token_obj.user_agent, token_obj.ip_address
        )

        return new_access_token, new_refresh_token, None

    @staticmethod
    def revoke_refresh_token(token: str) -> bool:
        """Revoke a refresh token"""
        try:
            refresh_token = RefreshToken.query.filter_by(token=token).first()
            if refresh_token:
                refresh_token.revoke()
                db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    @staticmethod
    def revoke_all_user_tokens(user_id: int | BigInteger) -> bool:
        """Revoke all refresh tokens for a user"""
        try:
            RefreshToken.query.filter_by(user_id=user_id, is_revoked=False).update(
                {"is_revoked": True}
            )
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    @staticmethod
    def cleanup_expired_tokens() -> int:
        """Remove expired tokens from database"""
        try:
            count_result = RefreshToken.query.filter(
                RefreshToken.expires_at < datetime.utcnow()
            ).delete()
            db.session.commit()
            return int(count_result) if count_result is not None else 0
        except Exception:
            db.session.rollback()
            return 0
