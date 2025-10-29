"""
Unit tests for database models
"""

from datetime import datetime, timedelta

import pytest

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.security import hash_password


@pytest.mark.unit
class TestUserModel:
    """Tests for User model"""

    def test_create_user(self, db_session):
        """Test creating a user"""
        user = User(
            email="newuser@example.com",
            username="newuser",
            password_hash=hash_password("Password123!"),
            first_name="New",
            last_name="User",
            is_active=True,
            is_verified=False,
        )
        db_session.add(user)
        db_session.commit()

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.username == "newuser"
        assert user.is_active is True
        assert user.is_verified is False
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_user_to_dict(self, sample_user):
        """Test user to dictionary conversion"""
        user_dict = sample_user.to_dict()

        assert user_dict["id"] == sample_user.id
        assert user_dict["email"] == sample_user.email
        assert user_dict["username"] == sample_user.username
        assert user_dict["first_name"] == sample_user.first_name
        assert user_dict["last_name"] == sample_user.last_name
        assert user_dict["is_active"] is True
        assert "password_hash" not in user_dict

    def test_user_to_dict_with_sensitive(self, sample_user):
        """Test user to dictionary with sensitive data"""
        user_dict = sample_user.to_dict(include_sensitive=True)

        assert "updated_at" in user_dict
        assert "password_hash" not in user_dict  # Still should not include password

    def test_user_repr(self, sample_user):
        """Test user string representation"""
        repr_str = repr(sample_user)
        assert "User" in repr_str
        assert sample_user.username in repr_str

    def test_user_unique_email(self, db_session, sample_user):
        """Test that email must be unique"""
        duplicate_user = User(
            email=sample_user.email,  # Same email
            username="differentuser",
            password_hash=hash_password("Password123!"),
        )
        db_session.add(duplicate_user)

        with pytest.raises(Exception):  # Should raise IntegrityError
            db_session.commit()

    def test_user_unique_username(self, db_session, sample_user):
        """Test that username must be unique"""
        duplicate_user = User(
            email="different@example.com",
            username=sample_user.username,  # Same username
            password_hash=hash_password("Password123!"),
        )
        db_session.add(duplicate_user)

        with pytest.raises(Exception):  # Should raise IntegrityError
            db_session.commit()


@pytest.mark.unit
class TestRefreshTokenModel:
    """Tests for RefreshToken model"""

    def test_create_refresh_token(self, db_session, sample_user):
        """Test creating a refresh token"""
        token = RefreshToken(
            user_id=sample_user.id,
            token="test_token_string",
            expires_at=datetime.utcnow() + timedelta(days=30),
            user_agent="Test User Agent",
            ip_address="127.0.0.1",
        )
        db_session.add(token)
        db_session.commit()

        assert token.id is not None
        assert token.user_id == sample_user.id
        assert token.token == "test_token_string"
        assert token.is_revoked is False
        assert token.created_at is not None

    def test_refresh_token_is_expired_false(self, db_session, sample_user):
        """Test token is not expired when expiry is in future"""
        token = RefreshToken(
            user_id=sample_user.id,
            token="test_token",
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        db_session.add(token)
        db_session.commit()

        assert token.is_expired() is False

    def test_refresh_token_is_expired_true(self, db_session, sample_user):
        """Test token is expired when expiry is in past"""
        token = RefreshToken(
            user_id=sample_user.id,
            token="test_token",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(token)
        db_session.commit()

        assert token.is_expired() is True

    def test_refresh_token_is_valid_when_not_revoked_or_expired(self, db_session, sample_user):
        """Test token is valid when not revoked and not expired"""
        token = RefreshToken(
            user_id=sample_user.id,
            token="test_token",
            expires_at=datetime.utcnow() + timedelta(days=1),
            is_revoked=False,
        )
        db_session.add(token)
        db_session.commit()

        assert token.is_valid() is True

    def test_refresh_token_is_valid_false_when_revoked(self, db_session, sample_user):
        """Test token is not valid when revoked"""
        token = RefreshToken(
            user_id=sample_user.id,
            token="test_token",
            expires_at=datetime.utcnow() + timedelta(days=1),
            is_revoked=True,
        )
        db_session.add(token)
        db_session.commit()

        assert token.is_valid() is False

    def test_refresh_token_is_valid_false_when_expired(self, db_session, sample_user):
        """Test token is not valid when expired"""
        token = RefreshToken(
            user_id=sample_user.id,
            token="test_token",
            expires_at=datetime.utcnow() - timedelta(days=1),
            is_revoked=False,
        )
        db_session.add(token)
        db_session.commit()

        assert token.is_valid() is False

    def test_refresh_token_revoke(self, db_session, sample_user):
        """Test revoking a token"""
        token = RefreshToken(
            user_id=sample_user.id,
            token="test_token",
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        db_session.add(token)
        db_session.commit()

        assert token.is_revoked is False
        token.revoke()
        assert token.is_revoked is True

    def test_refresh_token_to_dict(self, refresh_token_obj):
        """Test refresh token to dictionary conversion"""
        token_dict = refresh_token_obj.to_dict()

        assert token_dict["id"] == refresh_token_obj.id
        assert token_dict["user_id"] == refresh_token_obj.user_id
        assert token_dict["is_revoked"] == refresh_token_obj.is_revoked
        assert "created_at" in token_dict
        assert "expires_at" in token_dict
        assert "token" not in token_dict  # Token value should not be in dict

    def test_refresh_token_repr(self, refresh_token_obj):
        """Test refresh token string representation"""
        repr_str = repr(refresh_token_obj)
        assert "RefreshToken" in repr_str
        assert str(refresh_token_obj.user_id) in repr_str

    def test_refresh_token_relationship_with_user(self, db_session, sample_user):
        """Test relationship between refresh token and user"""
        token = RefreshToken(
            user_id=sample_user.id,
            token="test_token",
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        db_session.add(token)
        db_session.commit()

        # Access user through relationship
        assert token.user.id == sample_user.id
        assert token.user.username == sample_user.username

        # Access tokens through user
        user_tokens = sample_user.refresh_tokens.all()
        assert len(user_tokens) > 0
        assert token in user_tokens
