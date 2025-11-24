"""
User management service layer
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.security import hash_password
from app.utils.validators import (
    sanitize_string,
    validate_email,
    validate_password,
    validate_username,
)


class UserService:
    """Service for user management operations"""

    @staticmethod
    def create_user(
        session: Session,
        email: str,
        username: str,
        password: str,
        first_name: str | None = None,
        last_name: str | None = None,
        country_code: str = "USA",
        role: str = "public",
    ) -> tuple[User, None] | tuple[None, str]:
        """
        Create a new user with validation.

        Args:
            email: User email address
            username: User username (for validation, not stored)
            password: User password (plain text)
            first_name: Optional first name
            last_name: Optional last name
            country_code: ISO 3166-1 alpha-3 country code (default: "USA")
            role: User role (default: "public")

        Returns:
            Tuple of (User object, None) on success or (None, error_message) on failure
        """
        # Validate email
        is_valid, result = validate_email(email)
        if not is_valid:
            return None, result
        normalized_email = result

        # Validate username
        is_valid, error = validate_username(username)
        if not is_valid:
            return None, error

        # Validate password
        is_valid, error = validate_password(password)
        if not is_valid:
            return None, error

        # Check if email already exists
        if session.query(User).filter_by(email=normalized_email).first():
            return None, "Email already registered"

        # Check if username already exists (by checking email prefix)
        if session.query(User).filter(User.email.like(f"{username}@%")).first():
            return None, "Username already taken"

        # Create user
        try:
            user = User(
                email=normalized_email,
                password_hash=hash_password(password),
                first_name=sanitize_string(first_name, 100) if first_name else "User",
                last_name=sanitize_string(last_name, 100) if last_name else "",
                country_code=country_code,
                role=role,
                status="pending",
                email_verified=False,
            )

            session.add(user)
            session.commit()

            return user, None
        except Exception as e:
            session.rollback()
            return None, f"Failed to create user: {e!s}"

    @staticmethod
    def get_user_by_id(session: Session, user_id: int) -> User | None:
        """Get user by ID"""
        result = session.query(User).filter_by(user_id=user_id, status="active").first()
        return result

    @staticmethod
    def get_user_by_email(session: Session, email: str) -> User | None:
        """Get user by email"""
        result = session.query(User).filter_by(email=email).first()
        return result

    @staticmethod
    def get_user_by_username(session: Session, username: str) -> User | None:
        """Get user by username (searches by email prefix)"""
        # Username is derived from email, so search by email prefix
        result = session.query(User).filter(User.email.like(f"{username}@%")).first()
        return result

    @staticmethod
    def update_last_login(session: Session, user: User) -> None:
        """Update user's last login timestamp"""
        try:
            # Update via query to ensure it works across sessions
            session.query(User).filter_by(user_id=user.user_id).update(
                {"last_login": datetime.utcnow()}
            )
            session.commit()
        except Exception:
            session.rollback()

    @staticmethod
    def set_reset_token(session: Session, user: User, token: str, expires_at: datetime) -> bool:
        """Set password reset token for user"""
        try:
            user.reset_token = token  # type: ignore[assignment]
            user.reset_token_expires = expires_at  # type: ignore[assignment]
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False

    @staticmethod
    def clear_reset_token(session: Session, user: User) -> None:
        """Clear password reset token"""
        try:
            user.reset_token = None  # type: ignore[assignment]
            user.reset_token_expires = None  # type: ignore[assignment]
            session.commit()
        except Exception:
            session.rollback()

    @staticmethod
    def update_password(session: Session, user: User, new_password: str) -> tuple[bool, str]:
        """Update user password"""
        # Validate new password
        is_valid, error = validate_password(new_password)
        if not is_valid:
            return False, error

        try:
            user.password_hash = hash_password(new_password)  # type: ignore[assignment]
            session.commit()
            return True, ""
        except Exception as e:
            session.rollback()
            return False, f"Failed to update password: {e!s}"
