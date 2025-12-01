"""Custom exceptions for table-normalizer Lambda."""


class TableNormalizerError(Exception):
    """Base exception for table normalizer."""
    pass


class NormalizationError(TableNormalizerError):
    """Raised when table normalization fails."""
    pass


class S3Error(TableNormalizerError):
    """Raised when S3 operations fail."""
    pass

