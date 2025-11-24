"""
Unit tests for UserService
"""

import pytest

from app.models.user import User
from app.services.user_service import UserService


@pytest.mark.unit
class TestUserService:
    """Test UserService methods"""

    def test_get_user_by_id(self, db_session, sample_user):
        """Test getting user by ID"""
        user = UserService.get_user_by_id(db_session, sample_user.user_id)
        assert user is not None
        assert user.email == sample_user.email

    def test_get_user_by_id_not_found(self, db_session):
        """Test getting non-existent user"""
        user = UserService.get_user_by_id(db_session, 99999)
        assert user is None

    def test_get_user_by_email(self, db_session, sample_user):
        """Test getting user by email"""
        user = UserService.get_user_by_email(db_session, sample_user.email)
        assert user is not None
        assert user.user_id == sample_user.user_id

    def test_get_user_by_email_not_found(self, db_session):
        """Test getting non-existent user by email"""
        user = UserService.get_user_by_email(db_session, "nonexistent@example.com")
        assert user is None

    def test_update_user_first_name(self, db_session, sample_user):
        """Test updating user first name"""
        user, error = UserService.update_user(
            db_session, sample_user.user_id, {"first_name": "Jane"}
        )
        assert error is None
        assert user.first_name == "Jane"

    def test_update_user_invalid_email(self, db_session, sample_user):
        """Test updating user with invalid email"""
        user, error = UserService.update_user(
            db_session, sample_user.user_id, {"email": "invalid-email"}
        )
        assert user is None
        assert "Invalid email" in error

    def test_update_user_duplicate_email(self, db_session, sample_user):
        """Test updating user with duplicate email"""
        # Create another user
        other_user = User(
            first_name="Other",
            last_name="User",
            email="other@example.com",
            password_hash="hashed",
            role="public",
            status="active",
            country_code="USA",
        )
        db_session.add(other_user)
        db_session.commit()

        # Try to update sample_user with other_user's email
        user, error = UserService.update_user(
            db_session, sample_user.user_id, {"email": "other@example.com"}
        )
        assert user is None
        assert "already in use" in error

    def test_update_user_invalid_role(self, db_session, sample_user):
        """Test updating user with invalid role"""
        user, error = UserService.update_user(
            db_session, sample_user.user_id, {"role": "invalid_role"}
        )
        assert user is None
        assert "Role must be one of" in error

    def test_delete_user(self, db_session, sample_user):
        """Test deleting user"""
        user_id = sample_user.user_id
        success, error = UserService.delete_user(db_session, user_id)
        assert success is True
        assert error is None

        # Verify user is deleted
        user = UserService.get_user_by_id(db_session, user_id)
        assert user is None

    def test_delete_user_not_found(self, db_session):
        """Test deleting non-existent user"""
        success, error = UserService.delete_user(db_session, 99999)
        assert success is False
        assert "not found" in error

    def test_search_users(self, db_session, sample_user):
        """Test searching users"""
        users = UserService.search_users(db_session, "john")
        assert len(users) >= 1
        assert any(u.email == sample_user.email for u in users)

    def test_search_users_by_email(self, db_session, sample_user):
        """Test searching users by email"""
        users = UserService.search_users(db_session, "john.doe")
        assert len(users) >= 1
        assert users[0].email == sample_user.email

    def test_get_all_users(self, db_session, sample_user, admin_user):
        """Test getting all users with pagination"""
        result = UserService.get_all_users(db_session, page=1, per_page=10)
        assert result["total"] >= 2
        assert len(result["users"]) >= 2
        assert result["page"] == 1

    def test_get_all_users_filter_by_role(self, db_session, sample_user, admin_user):
        """Test filtering users by role"""
        result = UserService.get_all_users(db_session, role="admin")
        assert result["total"] >= 1
        assert all(u["role"] == "admin" for u in result["users"])
