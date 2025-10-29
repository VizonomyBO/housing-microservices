"""
Unit tests for AuthService
"""

from datetime import datetime, timedelta

import jwt
import pytest
from freezegun import freeze_time

from app.models.refresh_token import RefreshToken
from app.services.auth_service import AuthService


@pytest.mark.unit
class TestAuthenticateUser:
    """Tests for user authentication"""

    def test_authenticate_user_with_email_success(self, app, sample_user):
        """Test successful authentication with email"""
        with app.app_context():
            user, error = AuthService.authenticate_user("test@example.com", "TestPass123!")

            assert user is not None
            assert error is None
            assert user.id == sample_user.id
            assert user.email == sample_user.email

    def test_authenticate_user_with_username_success(self, app, sample_user):
        """Test successful authentication with username"""
        with app.app_context():
            user, error = AuthService.authenticate_user("testuser", "TestPass123!")

            assert user is not None
            assert error is None
            assert user.id == sample_user.id
            assert user.username == sample_user.username

    def test_authenticate_user_with_wrong_password(self, app, sample_user):
        """Test authentication failure with wrong password"""
        with app.app_context():
            user, error = AuthService.authenticate_user("test@example.com", "WrongPassword!")

            assert user is None
            assert error is not None
            assert "Invalid credentials" in error

    def test_authenticate_user_with_nonexistent_user(self, app):
        """Test authentication failure with non-existent user"""
        with app.app_context():
            user, error = AuthService.authenticate_user("nonexistent@example.com", "Password123!")

            assert user is None
            assert error is not None
            assert "Invalid credentials" in error

    def test_authenticate_user_with_inactive_user(self, app, inactive_user):
        """Test authentication failure with inactive user"""
        with app.app_context():
            user, error = AuthService.authenticate_user("inactive@example.com", "InactivePass123!")

            assert user is None
            assert error is not None


@pytest.mark.unit
class TestGenerateAccessToken:
    """Tests for access token generation"""

    def test_generate_access_token(self, app, sample_user):
        """Test access token generation"""
        with app.app_context():
            token = AuthService.generate_access_token(sample_user)

            assert token is not None
            assert isinstance(token, str)
            assert len(token) > 0

    def test_access_token_contains_correct_payload(self, app, sample_user):
        """Test that access token contains correct user information"""
        with app.app_context():
            token = AuthService.generate_access_token(sample_user)

            # Decode without verification to inspect payload
            payload = jwt.decode(token, options={"verify_signature": False})

            assert payload["user_id"] == sample_user.id
            assert payload["username"] == sample_user.username
            assert payload["email"] == sample_user.email
            assert payload["type"] == "access"
            assert "exp" in payload
            assert "iat" in payload

    @freeze_time("2024-01-01 12:00:00")
    def test_access_token_expiry(self, app, sample_user):
        """Test that access token has correct expiry time"""
        with app.app_context():
            token = AuthService.generate_access_token(sample_user)
            payload = jwt.decode(token, options={"verify_signature": False})

            expected_exp = datetime.utcnow() + app.config["JWT_ACCESS_TOKEN_EXPIRES"]
            actual_exp = datetime.fromtimestamp(payload["exp"])

            # Should be within 1 second
            assert abs((actual_exp - expected_exp).total_seconds()) < 1


@pytest.mark.unit
class TestGenerateRefreshToken:
    """Tests for refresh token generation"""

    def test_generate_refresh_token(self, app, db_session, sample_user):
        """Test refresh token generation"""
        with app.app_context():
            token = AuthService.generate_refresh_token(sample_user)

            assert token is not None
            assert isinstance(token, str)
            assert len(token) > 0

            # Check token was saved to database
            saved_token = RefreshToken.query.filter_by(token=token).first()
            assert saved_token is not None
            assert saved_token.user_id == sample_user.id

    def test_refresh_token_with_metadata(self, app, db_session, sample_user):
        """Test refresh token generation with user agent and IP"""
        with app.app_context():
            token = AuthService.generate_refresh_token(
                sample_user, user_agent="Mozilla/5.0", ip_address="192.168.1.1"
            )

            saved_token = RefreshToken.query.filter_by(token=token).first()
            assert saved_token.user_agent == "Mozilla/5.0"
            assert saved_token.ip_address == "192.168.1.1"

    def test_refresh_token_contains_correct_payload(self, app, db_session, sample_user):
        """Test that refresh token contains correct information"""
        with app.app_context():
            token = AuthService.generate_refresh_token(sample_user)
            payload = jwt.decode(token, options={"verify_signature": False})

            assert payload["user_id"] == sample_user.id
            assert payload["type"] == "refresh"
            assert "exp" in payload
            assert "iat" in payload


@pytest.mark.unit
class TestVerifyAccessToken:
    """Tests for access token verification"""

    def test_verify_valid_access_token(self, app, sample_user):
        """Test verification of valid access token"""
        with app.app_context():
            token = AuthService.generate_access_token(sample_user)
            payload, error = AuthService.verify_access_token(token)

            assert payload is not None
            assert error is None
            assert payload["user_id"] == sample_user.id
            assert payload["type"] == "access"

    def test_verify_expired_access_token(self, app, sample_user):
        """Test verification of expired access token"""
        with app.app_context():
            # Create token with very short expiry
            with freeze_time("2024-01-01 12:00:00"):
                token = AuthService.generate_access_token(sample_user)

            # Move time forward past expiry
            with freeze_time("2024-01-02 12:00:00"):
                payload, error = AuthService.verify_access_token(token)

                assert payload is None
                assert error is not None
                assert "expired" in error.lower()

    def test_verify_invalid_access_token(self, app):
        """Test verification of invalid token"""
        with app.app_context():
            payload, error = AuthService.verify_access_token("invalid_token")

            assert payload is None
            assert error is not None
            assert "Invalid token" in error

    def test_verify_refresh_token_as_access_token(self, app, db_session, sample_user):
        """Test that refresh token is rejected as access token"""
        with app.app_context():
            refresh_token = AuthService.generate_refresh_token(sample_user)
            payload, error = AuthService.verify_access_token(refresh_token)

            assert payload is None
            assert error is not None
            assert "Invalid token type" in error


@pytest.mark.unit
class TestVerifyRefreshToken:
    """Tests for refresh token verification"""

    def test_verify_valid_refresh_token(self, app, db_session, sample_user):
        """Test verification of valid refresh token"""
        with app.app_context():
            token = AuthService.generate_refresh_token(sample_user)
            token_obj, error = AuthService.verify_refresh_token(token)

            assert token_obj is not None
            assert error is None
            assert token_obj.user_id == sample_user.id

    def test_verify_revoked_refresh_token(self, app, db_session, sample_user):
        """Test verification of revoked refresh token"""
        with app.app_context():
            token = AuthService.generate_refresh_token(sample_user)

            # Revoke the token
            token_obj = RefreshToken.query.filter_by(token=token).first()
            token_obj.revoke()
            db_session.commit()

            # Try to verify
            result, error = AuthService.verify_refresh_token(token)

            assert result is None
            assert error is not None
            assert "invalid" in error.lower()

    def test_verify_expired_refresh_token(self, app, db_session, sample_user):
        """Test verification of expired refresh token"""
        with app.app_context():
            with freeze_time("2024-01-01 12:00:00"):
                token = AuthService.generate_refresh_token(sample_user)

            # Move time forward past expiry
            with freeze_time("2024-02-02 12:00:00"):
                result, error = AuthService.verify_refresh_token(token)

                assert result is None
                assert error is not None

    def test_verify_nonexistent_refresh_token(self, app):
        """Test verification of token not in database"""
        with app.app_context():
            # Create a valid JWT but not in database
            fake_payload = {
                "user_id": 999,
                "exp": datetime.utcnow() + timedelta(days=1),
                "type": "refresh",
            }
            fake_token = jwt.encode(fake_payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")

            result, error = AuthService.verify_refresh_token(fake_token)

            assert result is None
            assert error is not None
            assert "not found" in error.lower()


@pytest.mark.unit
class TestRefreshAccessToken:
    """Tests for token refresh functionality"""

    def test_refresh_access_token_success(self, app, db_session, sample_user):
        """Test successful token refresh"""
        with app.app_context():
            old_refresh_token = AuthService.generate_refresh_token(sample_user)

            new_access, new_refresh, error = AuthService.refresh_access_token(old_refresh_token)

            assert new_access is not None
            assert new_refresh is not None
            assert error is None

            # Old token should be revoked
            old_token_obj = RefreshToken.query.filter_by(token=old_refresh_token).first()
            assert old_token_obj.is_revoked is True

    def test_refresh_with_invalid_token(self, app):
        """Test token refresh with invalid token"""
        with app.app_context():
            new_access, new_refresh, error = AuthService.refresh_access_token("invalid_token")

            assert new_access is None
            assert new_refresh is None
            assert error is not None

    def test_refresh_with_inactive_user(self, app, db_session, inactive_user):
        """Test token refresh with inactive user"""
        with app.app_context():
            refresh_token = AuthService.generate_refresh_token(inactive_user)

            # Make user inactive
            inactive_user.is_active = False
            db_session.commit()

            new_access, new_refresh, error = AuthService.refresh_access_token(refresh_token)

            assert new_access is None
            assert new_refresh is None
            assert error is not None


@pytest.mark.unit
class TestRevokeTokens:
    """Tests for token revocation"""

    def test_revoke_refresh_token(self, app, db_session, sample_user):
        """Test revoking a single refresh token"""
        with app.app_context():
            token = AuthService.generate_refresh_token(sample_user)

            result = AuthService.revoke_refresh_token(token)

            assert result is True

            # Check token is revoked
            token_obj = RefreshToken.query.filter_by(token=token).first()
            assert token_obj.is_revoked is True

    def test_revoke_nonexistent_token(self, app):
        """Test revoking non-existent token"""
        with app.app_context():
            result = AuthService.revoke_refresh_token("nonexistent_token")

            # Should still return True (idempotent)
            assert result is True

    def test_revoke_all_user_tokens(self, app, db_session, sample_user):
        """Test revoking all tokens for a user"""
        with app.app_context():
            # Create multiple tokens
            AuthService.generate_refresh_token(sample_user)
            AuthService.generate_refresh_token(sample_user)
            AuthService.generate_refresh_token(sample_user)

            result = AuthService.revoke_all_user_tokens(sample_user.id)

            assert result is True

            # All tokens should be revoked
            tokens = RefreshToken.query.filter_by(user_id=sample_user.id).all()
            for token in tokens:
                assert token.is_revoked is True


@pytest.mark.unit
class TestCleanupExpiredTokens:
    """Tests for expired token cleanup"""

    def test_cleanup_expired_tokens(self, app, db_session, sample_user):
        """Test cleanup of expired tokens"""
        with app.app_context():
            # Create expired token
            with freeze_time("2024-01-01 12:00:00"):
                expired_token = RefreshToken(
                    user_id=sample_user.id,
                    token="expired_token",
                    expires_at=datetime.utcnow() - timedelta(days=1),
                )
                db_session.add(expired_token)
                db_session.commit()

            # Create valid token
            valid_token = AuthService.generate_refresh_token(sample_user)

            # Run cleanup
            count = AuthService.cleanup_expired_tokens()

            assert count >= 1

            # Expired token should be deleted
            assert RefreshToken.query.filter_by(token="expired_token").first() is None

            # Valid token should still exist
            assert RefreshToken.query.filter_by(token=valid_token).first() is not None
