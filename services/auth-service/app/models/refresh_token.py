"""
Refresh Token model for JWT token rotation
"""

from datetime import datetime

from app import db


class RefreshToken(db.Model):  # type: ignore[name-defined]
    """Refresh token model for secure token rotation"""

    __tablename__ = "refresh_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(db.String(500), unique=True, nullable=False, index=True)

    # Token metadata
    is_revoked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    # Device/session tracking
    user_agent = db.Column(db.String(500))
    ip_address = db.Column(db.String(45))

    def is_expired(self):
        """Check if token is expired"""
        return datetime.utcnow() > self.expires_at

    def is_valid(self):
        """Check if token is valid (not revoked and not expired)"""
        return not self.is_revoked and not self.is_expired()

    def revoke(self):
        """Revoke the token"""
        self.is_revoked = True

    def to_dict(self):
        """Convert token to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "is_revoked": self.is_revoked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    def __repr__(self):
        return f"<RefreshToken {self.id} for User {self.user_id}>"
