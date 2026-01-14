"""
Unit tests for validation utilities
"""

import pytest

from app.utils.validators import (
    sanitize_string,
    validate_email,
    validate_password,
    validate_username,
)


@pytest.mark.unit
class TestEmailValidation:
    """Tests for email validation"""

    def test_validate_email_valid(self):
        """Test validation of valid email addresses"""
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "first+last@subdomain.example.com",
            "123@example.com",
        ]

        for email in valid_emails:
            is_valid, result = validate_email(email)
            assert is_valid is True
            assert isinstance(result, str)

    def test_validate_email_invalid(self):
        """Test validation of invalid email addresses"""
        invalid_emails = ["notanemail", "@example.com", "test@", "test @example.com", ""]

        for email in invalid_emails:
            is_valid, error = validate_email(email)
            assert is_valid is False
            assert isinstance(error, str)
            assert len(error) > 0

    def test_validate_email_normalizes(self):
        """Test that email validation normalizes addresses"""
        is_valid, normalized = validate_email("TEST@EXAMPLE.COM")
        assert is_valid is True
        assert normalized == "test@example.com"

    def test_validate_email_empty(self):
        """Test validation of empty email"""
        is_valid, error = validate_email("")
        assert is_valid is False
        assert "required" in error.lower()


@pytest.mark.unit
class TestPasswordValidation:
    """Tests for password validation"""

    def test_validate_password_valid(self):
        """Test validation of valid passwords"""
        valid_passwords = ["TestPass123!", "MyP@ssw0rd", "Str0ng!Pass", "C0mplex#Password"]

        for password in valid_passwords:
            is_valid, error = validate_password(password)
            assert is_valid is True
            assert error == ""

    def test_validate_password_too_short(self):
        """Test validation of too short password"""
        is_valid, error = validate_password("Short1!")
        assert is_valid is False
        assert "at least 8 characters" in error.lower()

    def test_validate_password_too_long(self):
        """Test validation of too long password"""
        long_password = "A1!" + "x" * 126  # 129 characters
        is_valid, error = validate_password(long_password)
        assert is_valid is False
        assert "exceed 128 characters" in error.lower()

    def test_validate_password_no_uppercase(self):
        """Test validation of password without uppercase"""
        is_valid, error = validate_password("testpass123!")
        assert is_valid is False
        assert "uppercase" in error.lower()

    def test_validate_password_no_lowercase(self):
        """Test validation of password without lowercase"""
        is_valid, error = validate_password("TESTPASS123!")
        assert is_valid is False
        assert "lowercase" in error.lower()

    def test_validate_password_no_digit(self):
        """Test validation of password without digit"""
        is_valid, error = validate_password("TestPassword!")
        assert is_valid is False
        assert "digit" in error.lower()

    def test_validate_password_no_special_char(self):
        """Test validation of password without special character"""
        is_valid, error = validate_password("TestPassword123")
        assert is_valid is False
        assert "special character" in error.lower()

    def test_validate_password_empty(self):
        """Test validation of empty password"""
        is_valid, error = validate_password("")
        assert is_valid is False
        assert "required" in error.lower()


@pytest.mark.unit
class TestUsernameValidation:
    """Tests for username validation"""

    def test_validate_username_valid(self):
        """Test validation of valid usernames"""
        valid_usernames = ["user123", "test_user", "john-doe", "a12"]

        for username in valid_usernames:
            is_valid, error = validate_username(username)
            assert is_valid is True
            assert error == ""

    def test_validate_username_too_short(self):
        """Test validation of too short username"""
        is_valid, error = validate_username("ab")
        assert is_valid is False
        assert "at least 3 characters" in error.lower()

    def test_validate_username_too_long(self):
        """Test validation of too long username"""
        long_username = "a" * 81
        is_valid, error = validate_username(long_username)
        assert is_valid is False
        assert "exceed 80 characters" in error.lower()

    def test_validate_username_invalid_start(self):
        """Test validation of username not starting with letter"""
        invalid_usernames = ["123user", "_user", "-user"]

        for username in invalid_usernames:
            is_valid, error = validate_username(username)
            assert is_valid is False
            assert "start with a letter" in error.lower()

    def test_validate_username_invalid_characters(self):
        """Test validation of username with invalid characters"""
        invalid_usernames = ["test@user", "user name", "user.name", "user!"]

        for username in invalid_usernames:
            is_valid, _error = validate_username(username)
            assert is_valid is False

    def test_validate_username_empty(self):
        """Test validation of empty username"""
        is_valid, error = validate_username("")
        assert is_valid is False
        assert "required" in error.lower()


@pytest.mark.unit
class TestSanitizeString:
    """Tests for string sanitization"""

    def test_sanitize_string_normal(self):
        """Test sanitization of normal string"""
        result = sanitize_string("  test string  ")
        assert result == "test string"

    def test_sanitize_string_max_length(self):
        """Test sanitization with length limit"""
        long_string = "a" * 300
        result = sanitize_string(long_string, max_length=100)
        assert len(result) == 100

    def test_sanitize_string_empty(self):
        """Test sanitization of empty string"""
        result = sanitize_string("")
        assert result == ""

    def test_sanitize_string_none(self):
        """Test sanitization of None value"""
        result = sanitize_string(None)
        assert result == ""

    def test_sanitize_string_whitespace_only(self):
        """Test sanitization of whitespace-only string"""
        result = sanitize_string("    ")
        assert result == ""
