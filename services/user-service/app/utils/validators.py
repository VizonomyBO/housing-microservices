"""
Input validation utilities
"""

import re

from email_validator import EmailNotValidError, validate_email


def validate_email_format(email):
    """Validate email format"""
    try:
        # check_deliverability=False to skip DNS checks
        # in testing/dev environments
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def validate_password_strength(password):
    """
    Validate password strength
    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"

    return True, "Password is strong"


def validate_name(name, field_name="Name"):
    """Validate name fields"""
    if not name or not name.strip():
        return False, f"{field_name} is required"

    if len(name) < 2:
        return False, f"{field_name} must be at least 2 characters long"

    if len(name) > 100:
        return False, f"{field_name} must be less than 100 characters"

    return True, f"{field_name} is valid"


def validate_country_code(country_code):
    """Validate country code (ISO 3166-1 alpha-3)"""
    if not country_code:
        return False, "Country code is required"

    if len(country_code) != 3:
        return False, "Country code must be exactly 3 characters"

    if not country_code.isalpha():
        return False, "Country code must contain only letters"

    return True, "Country code is valid"


def validate_role(role):
    """Validate user role"""
    valid_roles = ["admin", "public", "government", "staff"]
    if role not in valid_roles:
        return False, f"Role must be one of: {', '.join(valid_roles)}"

    return True, "Role is valid"


def validate_status(status):
    """Validate user status"""
    valid_statuses = ["pending", "active", "inactive", "suspended"]
    if status not in valid_statuses:
        return False, f"Status must be one of: {', '.join(valid_statuses)}"

    return True, "Status is valid"
