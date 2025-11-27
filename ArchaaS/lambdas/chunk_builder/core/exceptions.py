"""Custom exceptions for chunk-builder Lambda."""


class ChunkBuilderError(Exception):
    """Base exception for chunk builder."""
    pass


class ChunkingError(ChunkBuilderError):
    """Raised when chunking fails."""
    pass


class S3Error(ChunkBuilderError):
    """Raised when S3 operations fail."""
    pass


class ValidationError(ChunkBuilderError):
    """Raised when input validation fails."""
    pass

