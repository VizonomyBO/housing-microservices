"""
Input validation utilities
"""

import re

from email_validator import EmailNotValidError
from email_validator import validate_email as email_validator


def validate_email(email: str) -> tuple[bool, str]:
    """
    Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email:
        return False, "Email is required"

    try:
        # Validate and normalize email
        valid = email_validator(email)
        return True, valid.email
    except EmailNotValidError as e:
        return False, str(e)


def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password strength.

    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not password:
        return False, "Password is required"

    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if len(password) > 128:
        return False, "Password must not exceed 128 characters"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"

    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;/~`]', password):
        return False, "Password must contain at least one special character"

    return True, ""


def validate_username(username: str) -> tuple[bool, str]:
    """
    Validate username format.

    Requirements:
    - 3-80 characters
    - Alphanumeric, underscores, hyphens only
    - Must start with a letter

    Args:
        username: Username to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not username:
        return False, "Username is required"

    if len(username) < 3:
        return False, "Username must be at least 3 characters long"

    if len(username) > 80:
        return False, "Username must not exceed 80 characters"

    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", username):
        return (
            False,
            "Username must start with a letter and contain only letters, numbers, underscores, and hyphens",
        )

    return True, ""


def sanitize_string(value: str, max_length: int = 255) -> str:
    """
    Sanitize a string input by trimming and limiting length.

    Args:
        value: String to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    if not value:
        return ""

    # Strip whitespace and limit length
    return value.strip()[:max_length]
