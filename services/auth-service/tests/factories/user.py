"""Factories for user-related models."""

from datetime import datetime, timedelta
from typing import Any, ClassVar

import factory

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.enums import UserStatus
from app.utils.security import hash_password
from tests.factories.base import BaseFactory

# Default test password for all factory-created users
DEFAULT_TEST_PASSWORD = "TestPassword123!"


class UserFactory(BaseFactory):
    """Factory for creating test users."""

    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"testuser{n}@example.com")
    username = factory.LazyAttribute(lambda obj: obj.email.split("@")[0])
    password_hash = factory.LazyFunction(lambda: hash_password(DEFAULT_TEST_PASSWORD))
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    country_code = "USA"
    role = "public"
    status = UserStatus.ACTIVE.value
    email_verified = True

    # Payload configuration for API-ready dicts
    payload_exclude: ClassVar[set[str]] = {
        "id",
        "user_id",
        "created_at",
        "updated_at",
        "password_hash",
        "reset_token",
        "reset_token_expires",
        "last_login",
    }

    @classmethod
    def build_payload(
        cls, password: str = DEFAULT_TEST_PASSWORD, **overrides: Any
    ) -> dict[str, Any]:
        """
        Build a dict payload suitable for API requests.

        This method creates a payload that includes the plain password
        instead of the hashed password for API testing.
        """
        payload = super().build_payload(**overrides)
        # Include plain password for registration/login tests
        payload["password"] = password
        return payload

    @classmethod
    def create_inactive(cls, **kwargs: Any) -> User:
        """Create an inactive user."""
        return cls.create(status=UserStatus.INACTIVE.value, **kwargs)

    @classmethod
    def create_suspended(cls, **kwargs: Any) -> User:
        """Create a suspended user."""
        return cls.create(status=UserStatus.SUSPENDED.value, **kwargs)

    @classmethod
    def create_pending(cls, **kwargs: Any) -> User:
        """Create a pending user."""
        return cls.create(status=UserStatus.PENDING.value, email_verified=False, **kwargs)

    @classmethod
    def create_with_password(cls, password: str, **kwargs: Any) -> User:
        """Create a user with a specific password."""
        kwargs["password_hash"] = hash_password(password)
        return cls.create(**kwargs)


class RefreshTokenFactory(BaseFactory):
    """Factory for creating refresh tokens."""

    class Meta:
        model = RefreshToken

    user = factory.SubFactory(UserFactory)
    user_id = factory.LazyAttribute(lambda obj: obj.user.user_id)
    token = factory.Faker("sha256")
    expires_at = factory.LazyFunction(lambda: datetime.utcnow() + timedelta(days=30))
    user_agent = factory.Faker("user_agent")
    ip_address = factory.Faker("ipv4")
    is_revoked = False

    # Payload configuration
    payload_exclude: ClassVar[set[str]] = {
        "id",
        "created_at",
        "updated_at",
        "user",
    }
    payload_foreign_key_map: ClassVar[dict[str, str]] = {"user_id": "user_id"}

    @classmethod
    def create_expired(cls, **kwargs: Any) -> RefreshToken:
        """Create an expired refresh token."""
        kwargs["expires_at"] = datetime.utcnow() - timedelta(days=1)
        return cls.create(**kwargs)

    @classmethod
    def create_revoked(cls, **kwargs: Any) -> RefreshToken:
        """Create a revoked refresh token."""
        return cls.create(is_revoked=True, **kwargs)
