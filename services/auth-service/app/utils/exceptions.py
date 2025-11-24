"""Custom exceptions for the authentication service."""


class AuthServiceException(Exception):
    """Base exception for authentication service errors."""


class AuthenticationError(AuthServiceException):
    """Raised when authentication fails."""


class AuthorizationError(AuthServiceException):
    """Raised when user lacks required permissions."""


class TokenError(AuthServiceException):
    """Base exception for token-related errors."""


class TokenExpiredError(TokenError):
    """Raised when a token has expired."""


class TokenInvalidError(TokenError):
    """Raised when a token is invalid or malformed."""


class UserNotFoundError(AuthServiceException):
    """Raised when a user is not found."""


class UserInactiveError(AuthServiceException):
    """Raised when attempting to authenticate an inactive user."""


class UserSuspendedError(AuthServiceException):
    """Raised when attempting to authenticate a suspended user."""


class UserPendingError(AuthServiceException):
    """Raised when attempting to authenticate a pending user."""


class ValidationError(AuthServiceException):
    """Raised when input validation fails."""


class DuplicateUserError(AuthServiceException):
    """Raised when attempting to create a user that already exists."""


class PasswordValidationError(ValidationError):
    """Raised when password validation fails."""
