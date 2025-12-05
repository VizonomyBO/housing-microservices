"""
Unit tests for User model
"""

import pytest

from app.models.user import User


@pytest.mark.unit
class TestUserModel:
    """Test User model"""

    def test_user_creation(self, db_session):
        """Test creating a user"""
        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password_hash="hashed_password",
            role="public",
            status="active",
            country_code="USA",
        )
        db_session.add(user)
        db_session.commit()

        assert user.user_id is not None
        assert user.email == "test@example.com"
        assert user.first_name == "Test"

    def test_user_properties(self, sample_user):
        """Test user properties"""
        assert sample_user.id == str(sample_user.user_id)
        assert sample_user.username == "john.doe"
        assert sample_user.is_active is True
        assert sample_user.is_verified is True
        assert sample_user.created_at == sample_user.date_created

    def test_user_to_dict(self, sample_user):
        """Test converting user to dictionary"""
        user_dict = sample_user.to_dict()
        assert user_dict["email"] == sample_user.email
        assert user_dict["first_name"] == sample_user.first_name
        assert user_dict["role"] == sample_user.role
        assert "password_hash" not in user_dict

    def test_user_to_dict_with_sensitive(self, sample_user, db_session):
        """Test converting user to dictionary with sensitive fields"""
        sample_user.notes = "Test notes"
        db_session.commit()

        user_dict = sample_user.to_dict(include_sensitive=True)
        assert "notes" in user_dict
        assert user_dict["notes"] == "Test notes"

    def test_is_active_setter(self, sample_user):
        """Test is_active setter"""
        sample_user.is_active = False
        assert sample_user.status == "inactive"

        sample_user.is_active = True
        assert sample_user.status == "active"

    def test_is_verified_setter(self, sample_user):
        """Test is_verified setter"""
        sample_user.is_verified = False
        assert sample_user.email_verified is False

        sample_user.is_verified = True
        assert sample_user.email_verified is True

    def test_username_property(self, sample_user):
        """Test username property"""
        assert sample_user.username == "john.doe"

        # Test with different email
        sample_user.email = "jane.smith@example.com"
        assert sample_user.username == "jane.smith"

    def test_user_repr(self, sample_user):
        """Test user string representation"""
        repr_str = repr(sample_user)
        assert "User" in repr_str
        assert str(sample_user.user_id) in repr_str
        assert sample_user.email in repr_str
