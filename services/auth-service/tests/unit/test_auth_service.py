"""
Unit tests for AuthService
"""

from datetime import datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from freezegun import freeze_time

from app.models.refresh_token import RefreshToken
from app.services.auth_service import AuthService


@pytest.mark.unit
class TestAuthenticateUser:
    """Tests for user authentication"""

    def test_authenticate_user_with_email_success(self, db_session, sample_user):
        """Test successful authentication with email"""
        from tests.factories.user import DEFAULT_TEST_PASSWORD

        user, error = AuthService.authenticate_user(
            db_session, sample_user.email, DEFAULT_TEST_PASSWORD
        )

        assert user is not None
        assert error is None
        assert user.user_id == sample_user.user_id
        assert user.email == sample_user.email

    def test_authenticate_user_with_username_success(self, db_session, sample_user):
        """Test successful authentication with username"""
        from tests.factories.user import DEFAULT_TEST_PASSWORD

        user, error = AuthService.authenticate_user(
            db_session, sample_user.username, DEFAULT_TEST_PASSWORD
        )

        assert user is not None
        assert error is None
        assert user.user_id == sample_user.user_id
        assert user.username == sample_user.username

    def test_authenticate_user_with_wrong_password(self, db_session, sample_user):
        """Test authentication failure with wrong password"""
        user, error = AuthService.authenticate_user(db_session, sample_user.email, "WrongPassword!")

        assert user is None
        assert error is not None
        assert "Invalid credentials" in error

    def test_authenticate_user_with_nonexistent_user(self, db_session):
        """Test authentication failure with non-existent user"""
        user, error = AuthService.authenticate_user(
            db_session, "nonexistent@example.com", "Password123!"
        )

        assert user is None
        assert error is not None
        assert "Invalid credentials" in error

    def test_authenticate_user_with_inactive_user(self, db_session, inactive_user):
        """Test authentication failure with inactive user"""
        from tests.factories.user import DEFAULT_TEST_PASSWORD

        user, error = AuthService.authenticate_user(
            db_session, inactive_user.email, DEFAULT_TEST_PASSWORD
        )

        assert user is None
        assert error is not None


@pytest.mark.unit
class TestGenerateAccessToken:
    """Tests for access token generation"""

    def test_generate_access_token(self, fastapi_app, sample_user):
        """Test access token generation"""
        config = fastapi_app.state.config
        token = AuthService.generate_access_token(sample_user, config)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_token_contains_correct_payload(self, fastapi_app, sample_user):
        """Test that access token contains correct user information"""
        config = fastapi_app.state.config
        token = AuthService.generate_access_token(sample_user, config)

        # Decode without verification to inspect payload
        payload = jwt.decode(token, options={"verify_signature": False})

        assert payload["user_id"] == str(sample_user.user_id)
        assert payload["username"] == sample_user.username
        assert payload["email"] == sample_user.email
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    @freeze_time("2024-01-01 12:00:00")
    def test_access_token_expiry(self, fastapi_app, sample_user):
        """Test that access token has correct expiry time"""
        config = fastapi_app.state.config
        token = AuthService.generate_access_token(sample_user, config)
        payload = jwt.decode(token, options={"verify_signature": False})

        expected_exp = datetime.utcnow() + config.JWT_ACCESS_TOKEN_EXPIRES
        actual_exp = datetime.fromtimestamp(payload["exp"])

        # Should be within 1 second
        assert abs((actual_exp - expected_exp).total_seconds()) < 1


@pytest.mark.unit
class TestGenerateRefreshToken:
    """Tests for refresh token generation"""

    def test_generate_refresh_token(self, db_session, fastapi_app, sample_user):
        """Test refresh token generation"""
        config = fastapi_app.state.config
        token = AuthService.generate_refresh_token(db_session, sample_user, None, None, config)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

        # Check token was saved to database
        saved_token = db_session.query(RefreshToken).filter_by(token=token).first()
        assert saved_token is not None
        assert saved_token.user_id == sample_user.user_id

    def test_refresh_token_with_metadata(self, db_session, fastapi_app, sample_user):
        """Test refresh token generation with user agent and IP"""
        config = fastapi_app.state.config
        token = AuthService.generate_refresh_token(
            db_session,
            sample_user,
            user_agent="Mozilla/5.0",
            ip_address="192.168.1.1",
            config=config,
        )

        saved_token = db_session.query(RefreshToken).filter_by(token=token).first()
        user_agent_val = saved_token.user_agent if saved_token else None
        ip_address_val = saved_token.ip_address if saved_token else None
        assert user_agent_val == "Mozilla/5.0"
        assert ip_address_val == "192.168.1.1"

    def test_refresh_token_contains_correct_payload(self, db_session, fastapi_app, sample_user):
        """Test that refresh token contains correct information"""
        config = fastapi_app.state.config
        token = AuthService.generate_refresh_token(db_session, sample_user, None, None, config)
        payload = jwt.decode(token, options={"verify_signature": False})

        assert payload["user_id"] == str(sample_user.user_id)
        assert payload["type"] == "refresh"
        assert "exp" in payload
        assert "iat" in payload


@pytest.mark.unit
class TestVerifyAccessToken:
    """Tests for access token verification"""

    def test_verify_valid_access_token(self, db_session, fastapi_app, sample_user):
        """Test verification of valid access token"""
        config = fastapi_app.state.config
        token = AuthService.generate_access_token(sample_user, config)
        payload, error = AuthService.verify_access_token(db_session, token, config)

        assert payload is not None
        assert error is None
        assert payload["user_id"] == str(sample_user.user_id)
        assert payload["type"] == "access"

    def test_verify_expired_access_token(self, db_session, fastapi_app, sample_user):
        """Test verification of expired access token"""
        config = fastapi_app.state.config
        # Create token with very short expiry
        with freeze_time("2024-01-01 12:00:00"):
            token = AuthService.generate_access_token(sample_user, config)

        # Move time forward past expiry
        with freeze_time("2024-01-02 12:00:00"):
            payload, error = AuthService.verify_access_token(db_session, token, config)

            assert payload is None
            assert error is not None
            assert "expired" in error.lower()

    def test_verify_invalid_access_token(self, db_session, fastapi_app):
        """Test verification of invalid token"""
        config = fastapi_app.state.config
        payload, error = AuthService.verify_access_token(db_session, "invalid_token", config)

        assert payload is None
        assert error is not None
        assert "Invalid token" in error

    def test_verify_refresh_token_as_access_token(self, db_session, fastapi_app, sample_user):
        """Test that refresh token is rejected as access token"""
        config = fastapi_app.state.config
        refresh_token = AuthService.generate_refresh_token(
            db_session, sample_user, None, None, config
        )
        payload, error = AuthService.verify_access_token(db_session, refresh_token, config)

        assert payload is None
        assert error is not None
        assert "Invalid token type" in error


@pytest.mark.unit
class TestVerifyRefreshToken:
    """Tests for refresh token verification"""

    def test_verify_valid_refresh_token(self, db_session, fastapi_app, sample_user):
        """Test verification of valid refresh token"""
        config = fastapi_app.state.config
        token = AuthService.generate_refresh_token(db_session, sample_user, None, None, config)
        token_obj, error = AuthService.verify_refresh_token(db_session, token, config)

        assert token_obj is not None
        assert error is None
        assert token_obj.user_id == sample_user.user_id

    def test_verify_revoked_refresh_token(self, db_session, fastapi_app, sample_user):
        """Test verification of revoked refresh token"""
        config = fastapi_app.state.config
        token = AuthService.generate_refresh_token(db_session, sample_user, None, None, config)

        # Revoke the token
        token_obj = db_session.query(RefreshToken).filter_by(token=token).first()
        token_obj.revoke()  # type: ignore[assignment]
        db_session.commit()

        # Try to verify
        result, error = AuthService.verify_refresh_token(db_session, token, config)

        assert result is None
        assert error is not None
        assert "invalid" in error.lower()

    def test_verify_expired_refresh_token(self, db_session, fastapi_app, sample_user):
        """Test verification of expired refresh token"""
        config = fastapi_app.state.config
        with freeze_time("2024-01-01 12:00:00"):
            token = AuthService.generate_refresh_token(db_session, sample_user, None, None, config)

        # Move time forward past expiry
        with freeze_time("2024-02-02 12:00:00"):
            result, error = AuthService.verify_refresh_token(db_session, token, config)

            assert result is None
            assert error is not None

    def test_verify_nonexistent_refresh_token(self, db_session, fastapi_app):
        """Test verification of token not in database"""
        config = fastapi_app.state.config
        # Create a valid JWT but not in database
        fake_payload = {
            "user_id": str(uuid4()),
            "exp": datetime.utcnow() + timedelta(days=1),
            "type": "refresh",
        }
        encoded = jwt.encode(fake_payload, config.JWT_SECRET_KEY, algorithm="HS256")
        fake_token = encoded.decode("utf-8") if isinstance(encoded, bytes) else encoded

        result, error = AuthService.verify_refresh_token(db_session, fake_token, config)

        assert result is None
        assert error is not None
        assert "not found" in error.lower()


@pytest.mark.unit
class TestRefreshAccessToken:
    """Tests for token refresh functionality"""

    def test_refresh_access_token_success(self, db_session, fastapi_app, sample_user):
        """Test successful token refresh"""
        config = fastapi_app.state.config
        old_refresh_token = AuthService.generate_refresh_token(
            db_session, sample_user, None, None, config
        )

        new_access, new_refresh, error = AuthService.refresh_access_token(
            db_session, old_refresh_token, config
        )

        assert new_access is not None
        assert new_refresh is not None
        assert error is None

        # Old token should be revoked
        old_token_obj = db_session.query(RefreshToken).filter_by(token=old_refresh_token).first()
        is_revoked_val = old_token_obj.is_revoked if old_token_obj else None
        assert is_revoked_val is True

    def test_refresh_with_invalid_token(self, db_session, fastapi_app):
        """Test token refresh with invalid token"""
        config = fastapi_app.state.config
        new_access, new_refresh, error = AuthService.refresh_access_token(
            db_session, "invalid_token", config
        )

        assert new_access is None
        assert new_refresh is None
        assert error is not None

    def test_refresh_with_inactive_user(self, db_session, fastapi_app, inactive_user):
        """Test token refresh with inactive user"""
        config = fastapi_app.state.config
        refresh_token = AuthService.generate_refresh_token(
            db_session, inactive_user, None, None, config
        )

        # Make user inactive
        inactive_user.status = "inactive"  # type: ignore[assignment]
        db_session.commit()

        new_access, new_refresh, error = AuthService.refresh_access_token(
            db_session, refresh_token, config
        )

        assert new_access is None
        assert new_refresh is None
        assert error is not None


@pytest.mark.unit
class TestRevokeTokens:
    """Tests for token revocation"""

    def test_revoke_refresh_token(self, db_session, fastapi_app, sample_user):
        """Test revoking a single refresh token"""
        config = fastapi_app.state.config
        token = AuthService.generate_refresh_token(db_session, sample_user, None, None, config)

        result = AuthService.revoke_refresh_token(db_session, token)

        assert result is True

        # Check token is revoked
        token_obj = db_session.query(RefreshToken).filter_by(token=token).first()
        is_revoked_val = token_obj.is_revoked if token_obj else None
        assert is_revoked_val is True

    def test_revoke_nonexistent_token(self, db_session):
        """Test revoking non-existent token"""
        result = AuthService.revoke_refresh_token(db_session, "nonexistent_token")

        # Should still return True (idempotent)
        assert result is True

    def test_revoke_all_user_tokens(self, db_session, fastapi_app, sample_user):
        """Test revoking all tokens for a user"""
        config = fastapi_app.state.config
        # Create multiple tokens
        AuthService.generate_refresh_token(db_session, sample_user, None, None, config)
        AuthService.generate_refresh_token(db_session, sample_user, None, None, config)
        AuthService.generate_refresh_token(db_session, sample_user, None, None, config)

        result = AuthService.revoke_all_user_tokens(db_session, sample_user.user_id)

        assert result is True

        # All tokens should be revoked
        tokens = db_session.query(RefreshToken).filter_by(user_id=sample_user.user_id).all()
        for token in tokens:
            is_revoked_val = token.is_revoked if token else None
            assert is_revoked_val is True


@pytest.mark.unit
class TestCleanupExpiredTokens:
    """Tests for expired token cleanup"""

    def test_cleanup_expired_tokens(self, db_session, fastapi_app, sample_user):
        """Test cleanup of expired tokens"""
        config = fastapi_app.state.config
        # Create expired token
        with freeze_time("2024-01-01 12:00:00"):
            expired_token = RefreshToken(
                user_id=sample_user.user_id,
                token="expired_token",
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            db_session.add(expired_token)
            db_session.commit()

        # Create valid token
        valid_token = AuthService.generate_refresh_token(
            db_session, sample_user, None, None, config
        )

        # Run cleanup
        count = AuthService.cleanup_expired_tokens(db_session)

        assert count >= 1

        # Expired token should be deleted
        assert db_session.query(RefreshToken).filter_by(token="expired_token").first() is None

        # Valid token should still exist
        assert db_session.query(RefreshToken).filter_by(token=valid_token).first() is not None
