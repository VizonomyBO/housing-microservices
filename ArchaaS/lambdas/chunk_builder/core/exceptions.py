"""Custom exceptions for chunk-builder Lambda."""


class ChunkBuilderError(Exception):
    """Base exception for chunk builder."""



class ChunkingError(ChunkBuilderError):
    """Raised when chunking fails."""



class S3Error(ChunkBuilderError):
    """Raised when S3 operations fail."""



class ValidationError(ChunkBuilderError):
    """Raised when input validation fails."""

