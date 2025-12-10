"""User service for managing user profiles and data."""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.sql import literal
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.validators import (
    validate_country_code,
    validate_email_format,
    validate_name,
    validate_role,
    validate_status,
)

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations"""

    @staticmethod
    def _coerce_uuid(value: UUID | str) -> UUID:
        if isinstance(value, UUID):
            return value
        return UUID(str(value))

    @staticmethod
    def get_user_by_id(session: Session, user_id: UUID | str) -> User | None:
        """Get user by ID"""
        try:
            user_uuid = UserService._coerce_uuid(user_id)
        except ValueError:
            logger.warning("Invalid user_id supplied", extra={"user_id": user_id})
            return None
        return session.query(User).filter_by(user_id=user_uuid).first()

    @staticmethod
    def get_user_by_email(session: Session, email: str) -> User | None:
        """Get user by email"""
        return session.query(User).filter_by(email=email).first()

    @staticmethod
    def get_all_users(
        session: Session,
        page: int = 1,
        per_page: int = 20,
        roles: list[str] | None = None,
        statuses: list[str] | None = None,
        countries: list[str] | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Get all users with pagination and filtering."""
        query = session.query(User)

        roles_filter = [role for role in (roles or []) if role]
        if roles_filter:
            query = query.filter(User.role.in_(roles_filter))

        status_filter = [status for status in (statuses or []) if status]
        if status_filter:
            query = query.filter(User.status.in_(status_filter))

        country_filter = [country.upper() for country in (countries or []) if country]
        if country_filter:
            query = query.filter(User.country_code.in_(country_filter))

        trimmed_search = search.strip() if search else ""
        if trimmed_search:
            pattern = f"%{trimmed_search}%"
            full_name = (User.first_name + literal(" ") + User.last_name)
            query = query.filter(
                or_(
                    User.email.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    full_name.ilike(pattern),
                )
            )

        query = query.order_by(User.date_created.desc())

        total = query.count()
        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()
        pages = (total + per_page - 1) // per_page if total > 0 else 0

        return {
            "users": [user.to_dict() for user in items],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1,
        }

    @staticmethod
    def update_user(
        session: Session,
        user_id: UUID | str,
        data: dict[str, Any],
        updated_by: UUID | str | None = None,
    ) -> tuple[User | None, str | None]:
        """Update user information"""
        try:
            user_uuid = UserService._coerce_uuid(user_id)
        except ValueError:
            logger.warning("Invalid user_id for update", extra={"user_id": user_id})
            return None, "Invalid user ID"

        user = UserService.get_user_by_id(session, user_uuid)
        if not user:
            logger.warning("User not found for update", extra={"user_id": str(user_uuid)})
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
                    "Invalid email format",
                    extra={"user_id": str(user_uuid), "email": data["email"]},
                )
                return None, "Invalid email format"

            existing_user = UserService.get_user_by_email(session, data["email"])
            if existing_user and existing_user.user_id != user_uuid:
                logger.warning(
                    "Email already in use",
                    extra={"user_id": str(user_uuid), "email": data["email"]},
                )
                return None, "Email already in use"

            user.email = data["email"]
            user.email_verified = False  # type: ignore[assignment]

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

        user.date_modified = datetime.now(UTC)  # type: ignore[assignment]

        try:
            session.commit()
            logger.info(
                "User updated successfully",
                extra={
                    "user_id": str(user_uuid),
                    "updated_by": str(updated_by) if updated_by else None,
                },
            )
            return user, None
        except IntegrityError as e:
            session.rollback()
            logger.error(
                "Database error during update",
                extra={"user_id": str(user_uuid), "error": str(e)},
            )
            return None, f"Database error: {e!s}"

    @staticmethod
    def delete_user(session: Session, user_id: UUID | str) -> tuple[bool, str | None]:
        """Delete a user"""
        try:
            user_uuid = UserService._coerce_uuid(user_id)
        except ValueError:
            logger.warning("Invalid user_id for deletion", extra={"user_id": user_id})
            return False, "Invalid user ID"

        user = UserService.get_user_by_id(session, user_uuid)
        if not user:
            logger.warning("User not found for deletion", extra={"user_id": str(user_uuid)})
            return False, "User not found"

        try:
            session.delete(user)
            session.commit()
            logger.info("User deleted", extra={"user_id": str(user_uuid)})
            return True, None
        except Exception as e:
            session.rollback()
            logger.error("Error deleting user", extra={"user_id": str(user_uuid), "error": str(e)})
            return False, f"Error deleting user: {e!s}"

    @staticmethod
    def search_users(session: Session, query: str, limit: int = 10) -> list[User]:
        """Search users by email, first name, or last name"""
        search_pattern = f"%{query}%"

        users = (
            session.query(User)
            .filter(
                or_(
                    User.email.ilike(search_pattern),
                    User.first_name.ilike(search_pattern),
                    User.last_name.ilike(search_pattern),
                )
            )
            .limit(limit)
            .all()
        )

        logger.info("User search executed", extra={"query": query, "results": len(users)})
        return users

    @staticmethod
    def update_last_login(session: Session, user_id: UUID | str) -> bool:
        """Update user's last login timestamp"""
        user = UserService.get_user_by_id(session, user_id)
        if not user:
            return False

        user.last_login = datetime.now(UTC)  # type: ignore[assignment]

        try:
            session.commit()
            logger.debug("Last login updated", extra={"user_id": str(user.user_id)})
            return True
        except Exception as e:
            session.rollback()
            logger.error(
                "Failed to update last login",
                extra={"user_id": str(user.user_id), "error": str(e)},
            )
            return False
