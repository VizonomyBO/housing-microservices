"""
Unit tests for validation utilities
"""

import pytest

from app.utils.validators import (
    validate_country_code,
    validate_email_format,
    validate_name,
    validate_password_strength,
    validate_role,
    validate_status,
)


@pytest.mark.unit
class TestValidators:
    """Test validation utility functions"""

    def test_validate_email_format_valid(self):
        """Test valid email formats"""
        assert validate_email_format("user@example.com") is True
        assert validate_email_format("test.user@domain.co.uk") is True
        assert validate_email_format("john.doe+tag@example.org") is True

    def test_validate_email_format_invalid(self):
        """Test invalid email formats"""
        assert validate_email_format("invalid") is False
        assert validate_email_format("@example.com") is False
        assert validate_email_format("user@") is False
        assert validate_email_format("user@.com") is False

    def test_validate_password_strength_valid(self):
        """Test valid password"""
        is_valid, msg = validate_password_strength("StrongP@ss123")
        assert is_valid is True
        assert "strong" in msg.lower()

    def test_validate_password_strength_too_short(self):
        """Test password too short"""
        is_valid, msg = validate_password_strength("Short1!")
        assert is_valid is False
        assert "8 characters" in msg

    def test_validate_password_strength_no_uppercase(self):
        """Test password without uppercase"""
        is_valid, msg = validate_password_strength("weakpass123!")
        assert is_valid is False
        assert "uppercase" in msg

    def test_validate_password_strength_no_lowercase(self):
        """Test password without lowercase"""
        is_valid, msg = validate_password_strength("WEAKPASS123!")
        assert is_valid is False
        assert "lowercase" in msg

    def test_validate_password_strength_no_digit(self):
        """Test password without digit"""
        is_valid, msg = validate_password_strength("WeakPass!!")
        assert is_valid is False
        assert "digit" in msg

    def test_validate_password_strength_no_special(self):
        """Test password without special character"""
        is_valid, msg = validate_password_strength("WeakPass123")
        assert is_valid is False
        assert "special character" in msg

    def test_validate_name_valid(self):
        """Test valid names"""
        is_valid, msg = validate_name("John")
        assert is_valid is True

        is_valid, msg = validate_name("Mary Jane")
        assert is_valid is True

    def test_validate_name_too_short(self):
        """Test name too short"""
        is_valid, msg = validate_name("J")
        assert is_valid is False
        assert "2 characters" in msg

    def test_validate_name_empty(self):
        """Test empty name"""
        is_valid, msg = validate_name("")
        assert is_valid is False
        assert "required" in msg

    def test_validate_name_too_long(self):
        """Test name too long"""
        long_name = "A" * 101
        is_valid, msg = validate_name(long_name)
        assert is_valid is False
        assert "100 characters" in msg

    def test_validate_country_code_valid(self):
        """Test valid country codes"""
        is_valid, msg = validate_country_code("USA")
        assert is_valid is True

        is_valid, msg = validate_country_code("GBR")
        assert is_valid is True

    def test_validate_country_code_invalid_length(self):
        """Test country code with wrong length"""
        is_valid, msg = validate_country_code("US")
        assert is_valid is False
        assert "3 characters" in msg

    def test_validate_country_code_empty(self):
        """Test empty country code"""
        is_valid, msg = validate_country_code("")
        assert is_valid is False
        assert "required" in msg

    def test_validate_country_code_non_alpha(self):
        """Test country code with non-alphabetic characters"""
        is_valid, msg = validate_country_code("US1")
        assert is_valid is False
        assert "only letters" in msg

    def test_validate_role_valid(self):
        """Test valid roles"""
        for role in ["admin", "public", "government", "staff"]:
            is_valid, msg = validate_role(role)
            assert is_valid is True

    def test_validate_role_invalid(self):
        """Test invalid role"""
        is_valid, msg = validate_role("invalid_role")
        assert is_valid is False
        assert "must be one of" in msg

    def test_validate_status_valid(self):
        """Test valid statuses"""
        for status in ["pending", "active", "inactive", "suspended"]:
            is_valid, msg = validate_status(status)
            assert is_valid is True

    def test_validate_status_invalid(self):
        """Test invalid status"""
        is_valid, msg = validate_status("invalid_status")
        assert is_valid is False
        assert "must be one of" in msg
