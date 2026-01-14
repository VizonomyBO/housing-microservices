"""User model for authentication and account management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CHAR, Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.types import GUID


class User(Base):  # type: ignore[misc,valid-type]
    """User model with secure password storage"""

    __tablename__ = "users"

    user_id = Column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(
        String(20), nullable=False, default="public", index=True
    )  # ENUM: 'admin', 'public', 'government', 'staff'
    status = Column(String(20), nullable=False, default="pending", index=True)
    country_code = Column(CHAR(3), nullable=False, default="USA", index=True)

    date_created = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    date_modified = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    created_by = Column(
        GUID(),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    notes = Column(Text, nullable=True)

    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)

    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    # Self-referential relationship for creator
    # Note: Temporarily simplified to avoid SQLAlchemy mapper initialization issues
    # The created_by foreign key still works for database queries

    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_country", "country_code"),
        Index("idx_user_role_status", "role", "status"),
    )

    @property
    def id(self):
        """Alias for user_id for backward compatibility"""
        return str(self.user_id) if self.user_id is not None else None

    @property
    def username(self):
        """Get username from email (for backward compatibility)"""
        return self.email.split("@")[0] if self.email else None

    @username.setter
    def username(self, value):
        """No-op setter for username compatibility (username is derived from email)."""

    @property
    def is_active(self):
        """Check if user is active based on status"""
        return self.status == "active"

    @is_active.setter
    def is_active(self, value):
        """Setter for is_active - updates status field"""
        self.status = "active" if value else "inactive"  # type: ignore[assignment]

    @property
    def is_verified(self):
        """Alias for email_verified"""
        return self.email_verified

    @is_verified.setter
    def is_verified(self, value):
        """Setter for is_verified - updates email_verified field"""
        self.email_verified = value

    @property
    def created_at(self):
        """Alias for date_created"""
        return self.date_created

    @property
    def updated_at(self):
        """Alias for date_modified"""
        return self.date_modified

    def to_dict(self, include_sensitive=False):
        """Convert user to dictionary"""

        def _as_str(value):
            if value is None:
                return None
            return str(value)

        data = {
            "id": _as_str(self.user_id),
            "user_id": _as_str(self.user_id),
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "email_verified": self.email_verified,
            "is_verified": self.is_verified,
            "is_active": self.is_active,
            "role": self.role,
            "status": self.status,
            "country_code": self.country_code,
            "date_created": self.date_created.isoformat() if self.date_created else None,
            "date_modified": self.date_modified.isoformat() if self.date_modified else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": _as_str(self.created_by),
        }

        if include_sensitive:
            data["notes"] = self.notes

        return data

    def __repr__(self):
        return f"<User {self.user_id}: {self.email}>"
