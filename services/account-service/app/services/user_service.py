"""
User management service layer
"""

from datetime import datetime

from app import db
from app.models.user import User
from app.utils.security import hash_password
from app.utils.validators import (
    sanitize_string,
    validate_email,
    validate_password,
)


class UserService:
    """Service for user management operations"""

    @staticmethod
    def create_user(
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        country_code: str = "USA",
        role: str = "public",
    ) -> tuple[User, None] | tuple[None, str]:
        """
        Create a new user with validation.

        Args:
            email: User email address
            password: User password (plain text)
            first_name: User first name (required)
            last_name: User last name (required)
            country_code: ISO country code (default: "USA")
            role: User role (default: "public")

        Returns:
            Tuple of (User object, None) on success or (None, error_message) on failure
        """
        # Validate email
        is_valid, result = validate_email(email)
        if not is_valid:
            return None, result
        normalized_email = result

        # Validate password
        is_valid, error = validate_password(password)
        if not is_valid:
            return None, error

        # Validate required fields
        if not first_name or not last_name:
            return None, "First name and last name are required"

        # Validate country code (should be 3 characters)
        if not country_code or len(country_code) != 3:
            return None, "Country code must be 3 characters (ISO format)"

        # Validate role
        valid_roles = ['admin', 'public', 'government', 'staff']
        if role not in valid_roles:
            return None, f"Role must be one of: {', '.join(valid_roles)}"

        # Check if email already exists
        if User.query.filter_by(email=normalized_email).first():
            return None, "Email already registered"

        # Create user
        try:
            user = User(
                email=normalized_email,
                password_hash=hash_password(password),
                first_name=sanitize_string(first_name, 100),
                last_name=sanitize_string(last_name, 100),
                country_code=country_code.upper(),
                role=role,
                status='pending',  # New users start as pending
                email_verified=False,
            )

            db.session.add(user)
            db.session.commit()

            return user, None
        except Exception as e:
            db.session.rollback()
            return None, f"Failed to create user: {str(e)}"

    @staticmethod
    def get_user_by_id(user_id: int, active_only: bool = True) -> User | None:
        """Get user by ID"""
        if active_only:
            result = User.query.filter_by(user_id=user_id, status='active').first()
        else:
            result = User.query.filter_by(user_id=user_id).first()
        return result  # type: ignore[no-any-return]

    @staticmethod
    def get_user_by_email(email: str) -> User | None:
        """Get user by email"""
        result = User.query.filter_by(email=email, status='active').first()
        return result  # type: ignore[no-any-return]

    @staticmethod
    def update_last_login(user: User) -> None:
        """Update user's last login timestamp (stored in date_modified)"""
        try:
            # Update date_modified to track last activity
            user.date_modified = datetime.utcnow()
            db.session.commit()
        except Exception:
            db.session.rollback()

    @staticmethod
    def set_reset_token(user: User, token: str, expires_at: datetime) -> bool:
        """Set password reset token for user"""
        try:
            user.reset_token = token
            user.reset_token_expires = expires_at
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    @staticmethod
    def clear_reset_token(user: User) -> None:
        """Clear password reset token"""
        try:
            user.reset_token = None
            user.reset_token_expires = None
            db.session.commit()
        except Exception:
            db.session.rollback()

    @staticmethod
    def update_password(user: User, new_password: str) -> tuple[bool, str]:
        """Update user password"""
        # Validate new password
        is_valid, error = validate_password(new_password)
        if not is_valid:
            return False, error

        try:
            user.password_hash = hash_password(new_password)
            db.session.commit()
            return True, ""
        except Exception as e:
            db.session.rollback()
            return False, f"Failed to update password: {str(e)}"

    @staticmethod
    def list_users(
        page: int = 1,
        per_page: int = 10,
        status: str | None = None,
        role: str | None = None,
    ) -> tuple[list[User], int]:
        """
        List users with pagination and optional filtering.

        Args:
            page: Page number (1-indexed)
            per_page: Number of items per page (max 100)
            status: Filter by status ('active', 'pending', 'inactive', 'suspended')
            role: Filter by role ('admin', 'public', 'government', 'staff')

        Returns:
            Tuple of (list of User objects, total count)
        """
        # Validate and clamp per_page
        per_page = max(1, min(per_page, 100))
        page = max(1, page)

        # Build query
        query = User.query

        # Apply status filter
        if status:
            valid_statuses = ['active', 'pending', 'inactive', 'suspended']
            if status in valid_statuses:
                query = query.filter_by(status=status)

        # Apply role filter
        if role:
            valid_roles = ['admin', 'public', 'government', 'staff']
            if role in valid_roles:
                query = query.filter_by(role=role)

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        users = query.order_by(User.date_created.desc()).offset((page - 1) * per_page).limit(per_page).all()

        return users, total  # type: ignore[return-value]
