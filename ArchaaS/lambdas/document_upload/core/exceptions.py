"""
Custom exceptions for document upload Lambda.
"""


class DocumentUploadError(Exception):
    """Base exception for document upload errors."""
    
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationError(DocumentUploadError):
    """Raised when request validation fails."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.details = details or {}


class DuplicateDocumentError(DocumentUploadError):
    """Raised when a duplicate document is detected."""
    
    def __init__(self, document_id: str, content_hash: str):
        super().__init__(
            f"Document with hash {content_hash} already exists",
            code="DUPLICATE_DOCUMENT",
        )
        self.document_id = document_id
        self.content_hash = content_hash


class DatabaseError(DocumentUploadError):
    """Raised when database operations fail."""
    
    def __init__(self, message: str):
        super().__init__(message, code="DATABASE_ERROR")


class S3Error(DocumentUploadError):
    """Raised when S3 operations fail."""
    
    def __init__(self, message: str):
        super().__init__(message, code="S3_ERROR")


class AuthorizationError(DocumentUploadError):
    """Raised when authorization fails."""
    
    def __init__(self, message: str):
        super().__init__(message, code="FORBIDDEN")

