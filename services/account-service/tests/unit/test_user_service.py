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

    def test_create_user_success(self, app, db_session):
        """Test successful user creation"""
        with app.app_context():
            user, error = UserService.create_user(
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
            assert user.is_active is True
            assert user.is_verified is False

    def test_create_user_without_optional_fields(self, app, db_session):
        """Test user creation without optional fields"""
        with app.app_context():
            user, error = UserService.create_user(
                email="minimal@example.com", username="minimaluser", password="MinPass123!"
            )

            assert user is not None
            assert error is None
            assert user.first_name is None
            assert user.last_name is None

    def test_create_user_with_invalid_email(self, app, db_session):
        """Test user creation with invalid email"""
        with app.app_context():
            user, error = UserService.create_user(
                email="invalid-email", username="testuser", password="TestPass123!"
            )

            assert user is None
            assert error is not None

    def test_create_user_with_invalid_username(self, app, db_session):
        """Test user creation with invalid username"""
        with app.app_context():
            user, error = UserService.create_user(
                email="test@example.com", username="ab", password="TestPass123!"  # Too short
            )

            assert user is None
            assert error is not None
            assert "at least 3 characters" in error.lower()

    def test_create_user_with_weak_password(self, app, db_session):
        """Test user creation with weak password"""
        with app.app_context():
            user, error = UserService.create_user(
                email="test@example.com", username="testuser", password="weak"  # Too weak
            )

            assert user is None
            assert error is not None

    def test_create_user_with_duplicate_email(self, app, db_session, sample_user):
        """Test user creation with duplicate email"""
        with app.app_context():
            user, error = UserService.create_user(
                email=sample_user.email, username="differentuser", password="TestPass123!"
            )

            assert user is None
            assert error is not None
            assert "Email already registered" in error

    def test_create_user_with_duplicate_username(self, app, db_session, sample_user):
        """Test user creation with duplicate username"""
        with app.app_context():
            user, error = UserService.create_user(
                email="different@example.com",
                username=sample_user.username,
                password="TestPass123!",
            )

            assert user is None
            assert error is not None
            assert "Username already taken" in error

    def test_create_user_normalizes_email(self, app, db_session):
        """Test that email is normalized"""
        with app.app_context():
            user, error = UserService.create_user(
                email="TEST@EXAMPLE.COM", username="testuser", password="TestPass123!"
            )

            assert user is not None
            assert user.email == "test@example.com"


@pytest.mark.unit
class TestGetUser:
    """Tests for user retrieval"""

    def test_get_user_by_id(self, app, sample_user):
        """Test getting user by ID"""
        with app.app_context():
            user = UserService.get_user_by_id(sample_user.id)

            assert user is not None
            assert user.id == sample_user.id
            assert user.email == sample_user.email

    def test_get_user_by_id_not_found(self, app):
        """Test getting non-existent user by ID"""
        with app.app_context():
            user = UserService.get_user_by_id(99999)

            assert user is None

    def test_get_user_by_id_inactive(self, app, inactive_user):
        """Test that inactive users are not returned"""
        with app.app_context():
            user = UserService.get_user_by_id(inactive_user.id)

            assert user is None  # Inactive users should not be returned

    def test_get_user_by_email(self, app, sample_user):
        """Test getting user by email"""
        with app.app_context():
            user = UserService.get_user_by_email(sample_user.email)

            assert user is not None
            assert user.email == sample_user.email

    def test_get_user_by_email_not_found(self, app):
        """Test getting non-existent user by email"""
        with app.app_context():
            user = UserService.get_user_by_email("nonexistent@example.com")

            assert user is None

    def test_get_user_by_username(self, app, sample_user):
        """Test getting user by username"""
        with app.app_context():
            user = UserService.get_user_by_username(sample_user.username)

            assert user is not None
            assert user.username == sample_user.username

    def test_get_user_by_username_not_found(self, app):
        """Test getting non-existent user by username"""
        with app.app_context():
            user = UserService.get_user_by_username("nonexistent")

            assert user is None


@pytest.mark.unit
class TestUpdateLastLogin:
    """Tests for updating last login timestamp"""

    def test_update_last_login(self, app, db_session, sample_user):
        """Test updating last login timestamp"""
        with app.app_context():
            original_last_login = sample_user.last_login

            UserService.update_last_login(sample_user)

            # Refetch user to get updated value
            updated_user = User.query.get(sample_user.id)
            assert updated_user.last_login is not None
            assert updated_user.last_login != original_last_login


@pytest.mark.unit
class TestResetToken:
    """Tests for password reset token management"""

    def test_set_reset_token(self, app, db_session, sample_user):
        """Test setting reset token"""
        with app.app_context():
            token = "test_reset_token"
            expires_at = datetime.utcnow() + timedelta(hours=1)

            result = UserService.set_reset_token(sample_user, token, expires_at)

            assert result is True

            # Verify token was set
            updated_user = User.query.get(sample_user.id)
            assert updated_user.reset_token == token
            assert updated_user.reset_token_expires == expires_at

    def test_clear_reset_token(self, app, db_session, sample_user):
        """Test clearing reset token"""
        with app.app_context():
            # First set a token
            sample_user.reset_token = "test_token"
            sample_user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
            db_session.commit()

            # Clear it
            UserService.clear_reset_token(sample_user)

            # Verify token was cleared
            updated_user = User.query.get(sample_user.id)
            assert updated_user.reset_token is None
            assert updated_user.reset_token_expires is None


@pytest.mark.unit
class TestUpdatePassword:
    """Tests for password update"""

    def test_update_password_success(self, app, db_session, sample_user):
        """Test successful password update"""
        with app.app_context():
            new_password = "NewPassword123!"
            success, error = UserService.update_password(sample_user, new_password)

            assert success is True
            assert error == ""

            # Verify password was changed
            from app.utils.security import verify_password

            updated_user = User.query.get(sample_user.id)
            assert verify_password(updated_user.password_hash, new_password) is True

    def test_update_password_with_weak_password(self, app, sample_user):
        """Test password update with weak password"""
        with app.app_context():
            success, error = UserService.update_password(sample_user, "weak")

            assert success is False
            assert error != ""

    def test_update_password_with_empty_password(self, app, sample_user):
        """Test password update with empty password"""
        with app.app_context():
            success, error = UserService.update_password(sample_user, "")

            assert success is False
            assert "required" in error.lower()
