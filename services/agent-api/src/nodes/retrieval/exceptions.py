"""Custom exceptions raised by retrieval nodes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NodeError(Exception):
    """Base structured exception that LangGraph can serialize."""

    code: str
    message: str
    details: dict[str, object] | None = None

    def __str__(self) -> str:  # pragma: no cover - error repr only
        return f"{self.code}: {self.message}"


class InputNormalizationError(NodeError):
    """Raised when InputNormalizer cannot satisfy guardrails."""


class AttachmentValidationError(NodeError):
    """Raised when attachment visibility or scope checks fail."""
