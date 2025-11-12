"""
Unit tests for security utilities
"""

import pytest

from app.utils.security import generate_reset_token, hash_password, verify_password


@pytest.mark.unit
class TestPasswordHashing:
    """Tests for password hashing functionality"""

    def test_hash_password_generates_valid_hash(self):
        """Test that hash_password generates a valid hash"""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password  # Hash should be different from plain text

    def test_hash_password_generates_unique_hashes(self):
        """Test that same password generates different hashes (due to salt)"""
        password = "TestPassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different due to random salt
        assert hash1 != hash2

    def test_verify_password_with_correct_password(self):
        """Test password verification with correct password"""
        password = "CorrectPassword123!"
        hashed = hash_password(password)

        assert verify_password(hashed, password) is True

    def test_verify_password_with_incorrect_password(self):
        """Test password verification with incorrect password"""
        password = "CorrectPassword123!"
        hashed = hash_password(password)

        assert verify_password(hashed, "WrongPassword123!") is False

    def test_verify_password_with_empty_password(self):
        """Test password verification with empty password"""
        password = "CorrectPassword123!"
        hashed = hash_password(password)

        assert verify_password(hashed, "") is False

    def test_verify_password_with_invalid_hash(self):
        """Test password verification with invalid hash"""
        result = verify_password("invalid_hash", "password")
        assert result is False


@pytest.mark.unit
class TestResetToken:
    """Tests for reset token generation"""

    def test_generate_reset_token_default_length(self):
        """Test token generation with default length"""
        token = generate_reset_token()

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_reset_token_custom_length(self):
        """Test token generation with custom length"""
        length = 64
        token = generate_reset_token(length)

        assert token is not None
        assert isinstance(token, str)
        # URL-safe base64 encoding varies in length, but should be substantial
        assert len(token) > length

    def test_generate_reset_token_uniqueness(self):
        """Test that generated tokens are unique"""
        token1 = generate_reset_token()
        token2 = generate_reset_token()

        assert token1 != token2

    def test_generate_reset_token_url_safe(self):
        """Test that generated token is URL safe"""
        token = generate_reset_token()

        # URL-safe tokens should not contain problematic characters
        assert "/" not in token or "%" in token  # If / exists, it should be encoded
        assert "+" not in token  # URL-safe base64 uses - instead
