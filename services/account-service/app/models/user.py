"""
User model for authentication and account management
"""

from datetime import datetime

from sqlalchemy import BigInteger, Index

from app import db


class User(db.Model):  # type: ignore[name-defined]
    """User model with secure password storage"""

    __tablename__ = "users"

    user_id = db.Column(BigInteger, primary_key=True, autoincrement=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(20),
        nullable=False,
        default="public",
        index=True
    )  # ENUM: 'admin', 'public', 'government', 'staff'
    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
        index=True
    )  # ENUM: 'active', 'inactive', 'suspended', 'pending'
    country_code = db.Column(db.CHAR(3), nullable=False, index=True)
    
    # Timestamps
    date_created = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    date_modified = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Additional fields
    created_by = db.Column(BigInteger, db.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Password reset fields
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    # Relationships
    refresh_tokens = db.relationship(
        "RefreshToken", backref="user", lazy="dynamic", cascade="all, delete-orphan", foreign_keys="RefreshToken.user_id"
    )
    creator = db.relationship(
        "User", remote_side=[user_id], backref="created_users"
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_country", "country_code"),
        Index("idx_user_role_status", "role", "status"),
    )

    def to_dict(self, include_sensitive=False):
        """Convert user to dictionary"""
        data = {
            "user_id": self.user_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "email_verified": self.email_verified,
            "role": self.role,
            "status": self.status,
            "country_code": self.country_code,
            "date_created": self.date_created.isoformat() if self.date_created else None,
            "date_modified": self.date_modified.isoformat() if self.date_modified else None,
            "created_by": self.created_by,
        }

        if include_sensitive:
            data["notes"] = self.notes

        return data

    def __repr__(self):
        return f"<User {self.user_id}: {self.email}>"
