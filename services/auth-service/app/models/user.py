"""
User model for authentication and account management
"""

from datetime import datetime

from sqlalchemy import BigInteger, Index

from app import db


class User(db.Model):  # type: ignore[name-defined]
    """User model with secure password storage"""

    __tablename__ = "users"

    user_id = db.Column(
        BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(20), nullable=False, default="public", index=True
    )  # ENUM: 'admin', 'public', 'government', 'staff'
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    country_code = db.Column(db.CHAR(3), nullable=False, default="USA", index=True)

    date_created = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    date_modified = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    created_by = db.Column(
        BigInteger().with_variant(db.Integer, "sqlite"),
        db.ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    notes = db.Column(db.Text, nullable=True)

    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)

    refresh_tokens = db.relationship(
        "RefreshToken",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
        foreign_keys="RefreshToken.user_id",
    )
    creator = db.relationship("User", remote_side=[user_id], backref="created_users")

    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_country", "country_code"),
        Index("idx_user_role_status", "role", "status"),
    )

    @property
    def id(self):
        """Alias for user_id for backward compatibility"""
        return self.user_id

    @property
    def username(self):
        """Get username from email (for backward compatibility)"""
        return self.email.split("@")[0] if self.email else None

    @username.setter
    def username(self, value):
        """Setter for username (no-op since username is derived from email)"""
        # Username is derived from email, so setting it has no effect
        # This setter exists for compatibility with tests that try to set it
        pass

    @property
    def is_active(self):
        """Check if user is active based on status"""
        return self.status == "active"

    @is_active.setter
    def is_active(self, value):
        """Setter for is_active - updates status field"""
        self.status = "active" if value else "inactive"

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
        data = {
            "id": self.id,
            "user_id": self.user_id,
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
            "created_by": self.created_by,
        }

        if include_sensitive:
            data["notes"] = self.notes

        return data

    def __repr__(self):
        return f"<User {self.user_id}: {self.email}>"
