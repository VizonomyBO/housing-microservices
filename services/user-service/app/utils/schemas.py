"""Standardized response schemas for API endpoints."""

from dataclasses import dataclass, field
from typing import Any

from app.utils.enums import ErrorCode


@dataclass
class ErrorDetail:
    """Detail about a specific field validation error."""

    field: str
    message: str
    type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"field": self.field, "message": self.message}
        if self.type:
            result["type"] = self.type
        return result


@dataclass
class ErrorResponse:
    """Standardized error response structure."""

    code: ErrorCode
    message: str
    details: list[ErrorDetail] = field(default_factory=list)

    def __post_init__(self):
        """Initialize defaults."""
        if self.details is None:
            self.details = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": [detail.to_dict() for detail in self.details],
        }


@dataclass
class SuccessResponse:
    """Standardized success response structure."""

    message: str
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"message": self.message}
        if self.data:
            result["data"] = self.data
        return result
