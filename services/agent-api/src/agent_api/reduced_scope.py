"""Reduced-scope feature flag helpers for the Agent API.

This module centralizes the configuration + runtime flag objects used when the
service operates in the "text-only, no-Valkey" demo mode described in
`docs/epics/035.md`. Keeping the helpers colocated prevents drift between the
environment-driven settings (`ReducedScopeSettings`) and the LangGraph-facing
state flags (`ReducedScopeFlags`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass(slots=True)
class ReducedScopeSettings:
    """Environment-driven toggles for reduced-scope operation."""

    enabled: bool = False
    use_real_tools: bool = False
    text_only_chunks: bool = True
    disable_valkey: bool = True
    disable_rate_limiting: bool = True
    emit_demo_events: bool = True
    allowed_chunk_types: tuple[str, ...] = ("text",)

    def __post_init__(self) -> None:
        if self.use_real_tools:
            # Real tooling mode mirrors production behavior even when reduced scope stays enabled.
            self.text_only_chunks = False
            self.disable_valkey = False
            self.disable_rate_limiting = False

    def is_enabled(self) -> bool:
        return self.enabled

    def text_only_mode(self) -> bool:
        return self.enabled and self.text_only_chunks

    def should_disable_valkey(self) -> bool:
        return self.enabled and self.disable_valkey

    def should_disable_rate_limiter(self) -> bool:
        return self.enabled and self.disable_rate_limiting

    def real_tooling_mode(self) -> bool:
        return self.enabled and self.use_real_tools

    def to_flags(self) -> ReducedScopeFlags:
        """Generate the runtime flags consumed by LangGraph state."""

        return ReducedScopeFlags(
            enabled=self.enabled,
            use_real_tools=self.use_real_tools,
            text_only_chunks=self.text_only_chunks,
            disable_valkey=self.disable_valkey,
            disable_rate_limiting=self.disable_rate_limiting,
            emit_demo_events=self.emit_demo_events,
            allowed_chunk_types=list(self.allowed_chunk_types),
        )

    def as_metadata(self) -> dict[str, str | bool | tuple[str, ...]]:
        """Generate metadata suitable for HTTP/SSE logging."""

        return {
            "enabled": self.enabled,
            "use_real_tools": self.use_real_tools,
            "text_only_chunks": self.text_only_chunks,
            "disable_valkey": self.disable_valkey,
            "disable_rate_limiting": self.disable_rate_limiting,
            "allowed_chunk_types": self.allowed_chunk_types,
        }


class ReducedScopeFlags(BaseModel):
    """Runtime flags injected into LangGraph state + ChatRequestContext."""

    enabled: bool = False
    use_real_tools: bool = False
    text_only_chunks: bool = True
    disable_valkey: bool = True
    disable_rate_limiting: bool = True
    emit_demo_events: bool = True
    allowed_chunk_types: list[str] = Field(default_factory=lambda: ["text"])

    def text_only_mode(self) -> bool:
        return self.enabled and self.text_only_chunks

    def describe(self) -> dict[str, bool | list[str]]:
        return {
            "enabled": self.enabled,
            "use_real_tools": self.use_real_tools,
            "text_only_chunks": self.text_only_chunks,
            "disable_valkey": self.disable_valkey,
            "disable_rate_limiting": self.disable_rate_limiting,
            "allowed_chunk_types": list(self.allowed_chunk_types),
        }

    def should_skip_capability(self, capability: str) -> bool:
        """Return True when a capability should be skipped during demo mode."""

        if not self.enabled:
            return False
        capability = capability.lower()
        if capability in {"numerical", "vision", "table", "image"}:
            return self.text_only_chunks
        return capability in {"valkey", "rate_limit"}


def coerce_allowed_chunk_types(raw: str | None) -> tuple[str, ...]:
    """Normalize comma-separated chunk type lists into a tuple."""

    if not raw:
        return ("text",)
    parts = [part.strip().lower() for part in raw.split(",") if part.strip()]
    return tuple(sorted(set(parts))) or ("text",)


def reduced_scope_demo_metadata(
    flags: ReducedScopeFlags | ReducedScopeSettings,
) -> dict[str, bool | list[str]]:
    """Return metadata payload for SSE/meta events when demo mode is active."""

    allowed = (
        list(flags.allowed_chunk_types)
        if isinstance(flags.allowed_chunk_types, Iterable)
        else list(flags.allowed_chunk_types or [])
    )
    return {
        "enabled": getattr(flags, "enabled", False),
        "use_real_tools": getattr(flags, "use_real_tools", False),
        "text_only_chunks": getattr(flags, "text_only_chunks", False),
        "allowed_chunk_types": allowed,
        "disable_valkey": getattr(flags, "disable_valkey", False),
        "disable_rate_limiting": getattr(flags, "disable_rate_limiting", False),
    }


__all__ = [
    "ReducedScopeFlags",
    "ReducedScopeSettings",
    "coerce_allowed_chunk_types",
    "reduced_scope_demo_metadata",
]
