"""Base factory class for SQLAlchemy models."""

from typing import Any, ClassVar, TypeVar

import factory
from sqlalchemy.orm import DeclarativeMeta, Session

ModelType = TypeVar("ModelType", bound=DeclarativeMeta)

# Thread-local storage for the current session
_session_context: dict[str, Session] = {}


def set_factory_session(session: Session) -> None:
    """Set the session for factories to use."""
    import threading

    _session_context[threading.current_thread().name] = session


def get_factory_session() -> Session | None:
    """Get the current session for factories."""
    import threading

    return _session_context.get(threading.current_thread().name)


def clear_factory_session() -> None:
    """Clear the current session for factories."""
    import threading

    _session_context.pop(threading.current_thread().name, None)


class BaseFactory(factory.Factory):
    """
    Base factory that provides helpers for SQLAlchemy models.

    This factory automatically persists created instances to the database
    and provides utilities for building API payloads.
    """

    payload_exclude: ClassVar[set[str]] = {
        "id",
        "user_id",
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
        # Get session from kwargs or context
        session = kwargs.pop("_session", None) or get_factory_session()
        if session is None:
            raise RuntimeError(
                "No database session available. "
                "Pass _session=session to create() or use set_factory_session(session) first."
            )

        # Filter out class variables that shouldn't be passed to the model
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ("payload_exclude", "payload_foreign_key_map")
        }
        instance = model_class(**filtered_kwargs)
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
