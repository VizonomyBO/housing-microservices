"""Factories for user-related models."""

from typing import Any, ClassVar

import factory

from app.models.user import User
from app.utils.enums import UserStatus
from tests.factories.base import BaseFactory


class UserFactory(BaseFactory):
    """Factory for creating test users."""

    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"testuser{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    country_code = "USA"
    role = "public"
    status = UserStatus.ACTIVE.value
    email_verified = True

    # Payload configuration for API-ready dicts
    payload_exclude: ClassVar[set[str]] = {
        "id",
        "created_at",
        "updated_at",
        "date_created",
        "date_modified",
        "created_by",
        "notes",
    }

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
