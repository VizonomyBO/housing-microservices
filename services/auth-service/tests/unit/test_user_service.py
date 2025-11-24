"""
Unit tests for UserService
"""

from datetime import datetime, timedelta

import pytest

from app.models.user import User
from app.services.user_service import UserService


@pytest.mark.unit
class TestCreateUser:
    """Tests for user creation"""

    def test_create_user_success(self, db_session):
        """Test successful user creation"""
        user, error = UserService.create_user(
            db_session,
            email="newuser@example.com",
            username="newuser",
            password="NewPass123!",
            first_name="New",
            last_name="User",
        )

        assert user is not None
        assert error is None
        assert user.email == "newuser@example.com"
        assert user.username == "newuser"
        assert user.first_name == "New"
        assert user.last_name == "User"
        assert user.status == "pending"  # New users start as pending
        assert user.is_active is False  # Pending users are not active
        assert user.is_verified is False

    def test_create_user_without_optional_fields(self, db_session):
        """Test user creation without optional fields"""
        user, error = UserService.create_user(
            db_session, email="minimal@example.com", username="minimaluser", password="MinPass123!"
        )

        assert user is not None
        assert error is None
        # first_name and last_name are required, so defaults are used
        assert user.first_name == "User"  # Default when None provided
        assert user.last_name == ""  # Default when None provided

    def test_create_user_with_invalid_email(self, db_session):
        """Test user creation with invalid email"""
        user, error = UserService.create_user(
            db_session, email="invalid-email", username="testuser", password="TestPass123!"
        )

        assert user is None
        assert error is not None

    def test_create_user_with_invalid_username(self, db_session):
        """Test user creation with invalid username"""
        user, error = UserService.create_user(
            db_session,
            email="test@example.com",
            username="ab",
            password="TestPass123!",  # Too short
        )

        assert user is None
        assert error is not None
        assert "at least 3 characters" in error.lower()

    def test_create_user_with_weak_password(self, db_session):
        """Test user creation with weak password"""
        user, error = UserService.create_user(
            db_session,
            email="test@example.com",
            username="testuser",
            password="weak",  # Too weak
        )

        assert user is None
        assert error is not None

    def test_create_user_with_duplicate_email(self, db_session, sample_user):
        """Test user creation with duplicate email"""
        user, error = UserService.create_user(
            db_session, email=sample_user.email, username="differentuser", password="TestPass123!"
        )

        assert user is None
        assert error is not None
        assert "Email already registered" in error

    def test_create_user_with_duplicate_username(self, db_session, sample_user):
        """Test user creation with duplicate username"""
        user, error = UserService.create_user(
            db_session,
            email="different@example.com",
            username=sample_user.username,
            password="TestPass123!",
        )

        assert user is None
        assert error is not None
        assert "Username already taken" in error

    def test_create_user_normalizes_email(self, db_session):
        """Test that email is normalized"""
        user, error = UserService.create_user(
            db_session, email="TEST@EXAMPLE.COM", username="testuser", password="TestPass123!"
        )

        assert user is not None
        assert user.email == "test@example.com"


@pytest.mark.unit
class TestGetUser:
    """Tests for user retrieval"""

    def test_get_user_by_id(self, db_session, sample_user):
        """Test getting user by ID"""
        user = UserService.get_user_by_id(db_session, sample_user.user_id)

        assert user is not None
        assert user.user_id == sample_user.user_id
        assert user.email == sample_user.email

    def test_get_user_by_id_not_found(self, db_session):
        """Test getting non-existent user by ID"""
        user = UserService.get_user_by_id(db_session, 99999)

        assert user is None

    def test_get_user_by_id_inactive(self, db_session, inactive_user):
        """Test that inactive users are not returned"""
        user = UserService.get_user_by_id(db_session, inactive_user.user_id)

        assert user is None  # Inactive users should not be returned

    def test_get_user_by_email(self, db_session, sample_user):
        """Test getting user by email"""
        user = UserService.get_user_by_email(db_session, sample_user.email)

        assert user is not None
        assert user.email == sample_user.email

    def test_get_user_by_email_not_found(self, db_session):
        """Test getting non-existent user by email"""
        user = UserService.get_user_by_email(db_session, "nonexistent@example.com")

        assert user is None

    def test_get_user_by_username(self, db_session, sample_user):
        """Test getting user by username"""
        user = UserService.get_user_by_username(db_session, sample_user.username)

        assert user is not None
        assert user.username == sample_user.username

    def test_get_user_by_username_not_found(self, db_session):
        """Test getting non-existent user by username"""
        user = UserService.get_user_by_username(db_session, "nonexistent")

        assert user is None


@pytest.mark.unit
class TestUpdateLastLogin:
    """Tests for updating last login timestamp"""

    def test_update_last_login(self, db_session, sample_user):
        """Test updating last login timestamp"""
        original_last_login = sample_user.last_login

        UserService.update_last_login(db_session, sample_user)

        # Refetch user to get updated value
        db_session.refresh(sample_user)
        updated_user = db_session.query(User).filter_by(user_id=sample_user.user_id).first()
        assert updated_user.last_login is not None
        assert updated_user.last_login != original_last_login


@pytest.mark.unit
class TestResetToken:
    """Tests for password reset token management"""

    def test_set_reset_token(self, db_session, sample_user):
        """Test setting reset token"""
        token = "test_reset_token"
        expires_at = datetime.utcnow() + timedelta(hours=1)

        result = UserService.set_reset_token(db_session, sample_user, token, expires_at)

        assert result is True

        # Verify token was set
        db_session.refresh(sample_user)
        updated_user = db_session.query(User).filter_by(user_id=sample_user.user_id).first()
        assert updated_user.reset_token == token
        assert updated_user.reset_token_expires == expires_at

    def test_clear_reset_token(self, db_session, sample_user):
        """Test clearing reset token"""
        # First set a token
        sample_user.reset_token = "test_token"  # type: ignore[assignment]
        sample_user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)  # type: ignore[assignment]
        db_session.commit()

        # Clear it
        UserService.clear_reset_token(db_session, sample_user)

        # Verify token was cleared
        db_session.refresh(sample_user)
        updated_user = db_session.query(User).filter_by(user_id=sample_user.user_id).first()
        assert updated_user.reset_token is None
        assert updated_user.reset_token_expires is None


@pytest.mark.unit
class TestUpdatePassword:
    """Tests for password update"""

    def test_update_password_success(self, db_session, sample_user):
        """Test successful password update"""
        new_password = "NewPassword123!"
        success, error = UserService.update_password(db_session, sample_user, new_password)

        assert success is True
        assert error == ""

        # Verify password was changed
        from app.utils.security import verify_password

        db_session.refresh(sample_user)
        updated_user = db_session.query(User).filter_by(user_id=sample_user.user_id).first()
        password_hash: str = updated_user.password_hash  # type: ignore[assignment]
        assert verify_password(password_hash, new_password) is True

    def test_update_password_with_weak_password(self, db_session, sample_user):
        """Test password update with weak password"""
        success, error = UserService.update_password(db_session, sample_user, "weak")

        assert success is False
        assert error != ""

    def test_update_password_with_empty_password(self, db_session, sample_user):
        """Test password update with empty password"""
        success, error = UserService.update_password(db_session, sample_user, "")

        assert success is False
        assert "required" in error.lower()
