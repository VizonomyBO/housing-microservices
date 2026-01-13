"""Base factory class for SQLAlchemy models."""

from typing import Any, ClassVar, TypeVar

import factory
from sqlalchemy.orm import DeclarativeMeta

from app.db import get_session

ModelType = TypeVar("ModelType", bound=DeclarativeMeta)


class BaseFactory(factory.Factory):
    """
    Base factory that provides helpers for SQLAlchemy models.

    This factory automatically persists created instances to the database
    and provides utilities for building API payloads.
    """

    payload_exclude: ClassVar[set[str]] = {
        "id",
        "created_at",
        "updated_at",
        "password_hash",
    }
    payload_foreign_key_map: ClassVar[dict[str, str]] = {}

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs) -> ModelType:
        """
        Create and persist a model instance.

        Overrides the default factory creation to persist to database.
        """
        instance = model_class(**kwargs)
        session = get_session()
        session.add(instance)
        session.commit()
        return instance

    @classmethod
    def create_batch(cls, size: int, **kwargs: Any) -> list[ModelType]:
        """
        Create a batch of persisted instances.
        """
        return [cls.create(**kwargs) for _ in range(size)]

    @classmethod
    def build_payload(cls, **overrides: Any) -> dict[str, Any]:
        """
        Build a dict payload suitable for API requests.

        The default implementation removes bookkeeping fields (id/timestamps)
        and sensitive fields (password_hash) while keeping data suitable for
        API requests.
        """
        raw_payload: dict[str, Any] = factory.build(dict, FACTORY_CLASS=cls, **overrides)
        payload: dict[str, Any] = {}

        for key, value in raw_payload.items():
            if key in cls.payload_exclude:
                continue

            # Handle foreign key mappings
            mapped_key = cls.payload_foreign_key_map.get(key)
            if mapped_key:
                payload[mapped_key] = cls._coerce_identifier(value)
                continue

            # Convert values to JSON-serializable types
            if hasattr(value, "id"):  # SQLAlchemy model instance
                continue
            if hasattr(value, "isoformat"):  # datetime/date objects
                payload[key] = value.isoformat()
            else:
                payload[key] = value

        return payload

    @staticmethod
    def _coerce_identifier(value: Any) -> str | None:
        """
        Convert identifiers to JSON-serializable values.
        """
        if value is None:
            return None
        return str(value)
