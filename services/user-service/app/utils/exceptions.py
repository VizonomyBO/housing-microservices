"""Custom exceptions for the user service."""


class UserServiceException(Exception):
    """Base exception for user service errors."""


class UserNotFoundError(UserServiceException):
    """Raised when a user is not found."""


class UserAlreadyExistsError(UserServiceException):
    """Raised when attempting to create a user that already exists."""


class ValidationError(UserServiceException):
    """Raised when input validation fails."""


class AuthenticationError(UserServiceException):
    """Raised when authentication fails."""


class AuthorizationError(UserServiceException):
    """Raised when user lacks required permissions."""
