"""Custom exceptions for marker-converter Lambda."""


class MarkerConverterError(Exception):
    """Base exception for marker converter."""



class ConversionError(MarkerConverterError):
    """Raised when document conversion fails."""



class ConversionTransientError(ConversionError):
    """Transient conversion error that can be retried."""



class S3Error(MarkerConverterError):
    """Raised when S3 operations fail."""



class ValidationError(MarkerConverterError):
    """Raised when input validation fails."""



class ModelLoadError(MarkerConverterError):
    """Raised when Marker models fail to load."""

