"""
Refresh Token model for JWT token rotation
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class RefreshToken(Base):  # type: ignore[misc,valid-type]
    """Refresh token model for secure token rotation"""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token = Column(String(500), unique=True, nullable=False, index=True)

    # Token metadata
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    # Device/session tracking
    user_agent = Column(String(500))
    ip_address = Column(String(45))

    # Relationship
    user = relationship("User", back_populates="refresh_tokens")

    def is_expired(self):
        """Check if token is expired"""
        return datetime.utcnow() > self.expires_at

    def is_valid(self):
        """Check if token is valid (not revoked and not expired)"""
        return not self.is_revoked and not self.is_expired()

    def revoke(self):
        """Revoke the token"""
        self.is_revoked = True  # type: ignore[assignment]

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
