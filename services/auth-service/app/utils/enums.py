"""Enums for standardized error codes and status values."""

from enum import Enum


class ErrorCode(str, Enum):
    """Enum for standardized error codes used in API responses."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"
    ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
    ACCOUNT_PENDING = "ACCOUNT_PENDING"


class UserStatus(str, Enum):
    """Enum for user account status values."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class TokenType(str, Enum):
    """Enum for JWT token types."""

    ACCESS = "access"
    REFRESH = "refresh"
