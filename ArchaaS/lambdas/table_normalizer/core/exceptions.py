"""Custom exceptions for table-normalizer Lambda."""


class TableNormalizerError(Exception):
    """Base exception for table normalizer."""


class NormalizationError(TableNormalizerError):
    """Raised when table normalization fails."""


class S3Error(TableNormalizerError):
    """Raised when S3 operations fail."""
