"""Custom exceptions for preflight-validator Lambda."""


class PreflightError(Exception):
    """Base exception for preflight validator."""


class ValidationError(PreflightError):
    """Raised when document validation fails."""


class DuplicateDocumentError(PreflightError):
    """Raised when a duplicate document is detected."""

    def __init__(self, message: str, existing_document_id: str):
        super().__init__(message)
        self.existing_document_id = existing_document_id


class MimeTypeError(ValidationError):
    """Raised when MIME type validation fails."""


class DatabaseError(PreflightError):
    """Raised when database operations fail."""


class S3Error(PreflightError):
    """Raised when S3 operations fail."""


class StepFunctionError(PreflightError):
    """Raised when Step Function operations fail."""
