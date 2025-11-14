"""
User service for managing user profiles and data
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, cast

from sqlalchemy.exc import IntegrityError

from app import db
from app.models.user import User
from app.utils.validators import (
    validate_email_format,
    validate_name,
    validate_country_code,
    validate_role,
    validate_status,
)

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations"""

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[User]:
        """Get user by ID"""
        result = User.query.filter_by(user_id=user_id).first()
        return cast(Optional[User], result)

    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        """Get user by email"""
        result = User.query.filter_by(email=email).first()
        return cast(Optional[User], result)

    @staticmethod
    def get_all_users(
        page: int = 1,
        per_page: int = 20,
        role: Optional[str] = None,
        status: Optional[str] = None,
        country_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get all users with pagination and filtering"""
        query = User.query

        if role:
            query = query.filter_by(role=role)
        if status:
            query = query.filter_by(status=status)
        if country_code:
            query = query.filter_by(country_code=country_code)

        query = query.order_by(User.date_created.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            "users": [user.to_dict() for user in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "per_page": pagination.per_page,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        }

    @staticmethod
    def update_user(
        user_id: int, data: Dict[str, Any], updated_by: Optional[int] = None
    ) -> tuple[Optional[User], Optional[str]]:
        """Update user information"""
        user = UserService.get_user_by_id(user_id)
        if not user:
            logger.warning("User not found for update", extra={"user_id": user_id})
            return None, "User not found"
        if "first_name" in data:
            is_valid, message = validate_name(data["first_name"], "First name")
            if not is_valid:
                return None, message
            user.first_name = data["first_name"]

        if "last_name" in data:
            is_valid, message = validate_name(data["last_name"], "Last name")
            if not is_valid:
                return None, message
            user.last_name = data["last_name"]

        if "email" in data:
            if not validate_email_format(data["email"]):
                logger.warning(
                    "Invalid email format", extra={"user_id": user_id, "email": data["email"]}
                )
                return None, "Invalid email format"

            existing_user = UserService.get_user_by_email(data["email"])
            if existing_user and existing_user.user_id != user_id:
                logger.warning(
                    "Email already in use", extra={"user_id": user_id, "email": data["email"]}
                )
                return None, "Email already in use"

            user.email = data["email"]
            user.email_verified = False

        if "country_code" in data:
            is_valid, message = validate_country_code(data["country_code"])
            if not is_valid:
                return None, message
            user.country_code = data["country_code"].upper()

        if "role" in data:
            is_valid, message = validate_role(data["role"])
            if not is_valid:
                return None, message
            user.role = data["role"]

        if "status" in data:
            is_valid, message = validate_status(data["status"])
            if not is_valid:
                return None, message
            user.status = data["status"]

        if "notes" in data:
            user.notes = data["notes"]

        user.date_modified = datetime.utcnow()

        try:
            db.session.commit()
            logger.info(
                "User updated successfully", extra={"user_id": user_id, "updated_by": updated_by}
            )
            return user, None
        except IntegrityError as e:
            db.session.rollback()
            logger.error(
                "Database error during update", extra={"user_id": user_id, "error": str(e)}
            )
            return None, f"Database error: {str(e)}"

    @staticmethod
    def delete_user(user_id: int) -> tuple[bool, Optional[str]]:
        """Delete a user"""
        user = UserService.get_user_by_id(user_id)
        if not user:
            logger.warning("User not found for deletion", extra={"user_id": user_id})
            return False, "User not found"

        try:
            db.session.delete(user)
            db.session.commit()
            logger.info("User deleted", extra={"user_id": user_id})
            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error("Error deleting user", extra={"user_id": user_id, "error": str(e)})
            return False, f"Error deleting user: {str(e)}"

    @staticmethod
    def search_users(query: str, limit: int = 10) -> List[User]:
        """Search users by email, first name, or last name"""
        search_pattern = f"%{query}%"

        users = (
            User.query.filter(
                db.or_(
                    User.email.ilike(search_pattern),
                    User.first_name.ilike(search_pattern),
                    User.last_name.ilike(search_pattern),
                )
            )
            .limit(limit)
            .all()
        )

        logger.info("User search executed", extra={"query": query, "results": len(users)})
        return cast(List[User], users)

    @staticmethod
    def update_last_login(user_id: int) -> bool:
        """Update user's last login timestamp"""
        user = UserService.get_user_by_id(user_id)
        if not user:
            return False

        user.last_login = datetime.utcnow()

        try:
            db.session.commit()
            logger.debug("Last login updated", extra={"user_id": user_id})
            return True
        except Exception as e:
            db.session.rollback()
            logger.error("Failed to update last login", extra={"user_id": user_id, "error": str(e)})
            return False
