"""
Custom exceptions for preflight validator Lambda.

Exception types are designed to integrate with Step Function error handling:
- ValidationPermanentError: Non-retryable validation failures (routes to DeadLetter)
- ValidationTransientError: Retryable failures (triggers Step Function retry)
- DuplicateDocumentError: Document deduplication (routes to HandleDuplicate)
"""


class PreflightError(Exception):
    """Base exception for preflight validation errors."""
    
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationPermanentError(PreflightError):
    """
    Raised for non-retryable validation failures.
    
    Examples:
    - Unsupported file type
    - File too large
    - Magic bytes mismatch
    - Document not found
    """
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="VALIDATION_PERMANENT_ERROR")
        self.details = details or {}


class ValidationTransientError(PreflightError):
    """
    Raised for retryable validation failures.
    
    Examples:
    - S3 temporary unavailability
    - Database connection timeout
    - Network transient issues
    """
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="VALIDATION_TRANSIENT_ERROR")
        self.details = details or {}


class DuplicateDocumentError(PreflightError):
    """
    Raised when document deduplicates against existing document.
    
    This triggers the HandleDuplicate state in the Step Function,
    which skips processing and links to the existing document.
    """
    
    def __init__(
        self,
        document_id: str,
        existing_document_id: str,
        content_hash: str,
    ):
        super().__init__(
            f"Document {document_id} deduplicates against {existing_document_id}",
            code="DUPLICATE_DOCUMENT",
        )
        self.document_id = document_id
        self.existing_document_id = existing_document_id
        self.content_hash = content_hash


class S3Error(PreflightError):
    """Raised when S3 operations fail."""
    
    def __init__(self, message: str, retryable: bool = True):
        code = "S3_TRANSIENT_ERROR" if retryable else "S3_PERMANENT_ERROR"
        super().__init__(message, code=code)
        self.retryable = retryable


class DatabaseError(PreflightError):
    """Raised when database operations fail."""
    
    def __init__(self, message: str, retryable: bool = True):
        code = "DATABASE_TRANSIENT_ERROR" if retryable else "DATABASE_PERMANENT_ERROR"
        super().__init__(message, code=code)
        self.retryable = retryable


