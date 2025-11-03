"""
Document model for file management and validation
"""

from datetime import datetime

from sqlalchemy import BigInteger, Index

from app import db


class Document(db.Model):  # type: ignore[name-defined]
    """Document model for file uploads and management"""

    __tablename__ = "documents"

    document_id = db.Column(BigInteger, primary_key=True, autoincrement=True)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(BigInteger, nullable=False)
    file_type = db.Column(db.String(100), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    file_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)  # SHA-256 hash
    country_code = db.Column(db.CHAR(3), nullable=False, index=True)
    
    # Timestamps
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    date_modified = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # User tracking
    user_uploaded = db.Column(BigInteger, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    source = db.Column(db.String(255), nullable=True)
    
    # Validation tracking
    validated = db.Column(db.Boolean, default=False, nullable=False)
    validated_by = db.Column(BigInteger, db.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    validated_at = db.Column(db.DateTime, nullable=True)
    
    # Status and access control
    document_status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
        index=True
    )  # ENUM: 'pending', 'processing', 'validated', 'rejected', 'archived'
    access_level = db.Column(
        db.String(20),
        nullable=False,
        default="internal",
        index=True
    )  # ENUM: 'public', 'restricted', 'confidential', 'internal'

    # Relationships
    uploader = db.relationship(
        "User", foreign_keys=[user_uploaded], backref="uploaded_documents"
    )
    validator = db.relationship(
        "User", foreign_keys=[validated_by], backref="validated_documents"
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_document_country_status", "country_code", "document_status"),
        Index("idx_document_user_date", "user_uploaded", "date_uploaded"),
        Index("idx_document_access_level", "access_level"),
    )

    def to_dict(self):
        """Convert document to dictionary"""
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "mime_type": self.mime_type,
            "file_hash": self.file_hash,
            "country_code": self.country_code,
            "date_uploaded": self.date_uploaded.isoformat() if self.date_uploaded else None,
            "date_modified": self.date_modified.isoformat() if self.date_modified else None,
            "user_uploaded": self.user_uploaded,
            "source": self.source,
            "validated": self.validated,
            "validated_by": self.validated_by,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "document_status": self.document_status,
            "access_level": self.access_level,
        }

    def __repr__(self):
        return f"<Document {self.document_id}: {self.filename}>"

