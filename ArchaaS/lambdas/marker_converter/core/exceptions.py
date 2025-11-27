"""Custom exceptions for marker-converter Lambda."""


class MarkerConverterError(Exception):
    """Base exception for marker converter."""
    pass


class ConversionError(MarkerConverterError):
    """Raised when document conversion fails."""
    pass


class ConversionTransientError(ConversionError):
    """Transient conversion error that can be retried."""
    pass


class S3Error(MarkerConverterError):
    """Raised when S3 operations fail."""
    pass


class ValidationError(MarkerConverterError):
    """Raised when input validation fails."""
    pass


class ModelLoadError(MarkerConverterError):
    """Raised when Marker models fail to load."""
    pass

