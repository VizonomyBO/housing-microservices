"""Context for tools to access per-request services."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.auth.validator import AuthContext
from agent_api.services.retrieval import (
    RetrievalContext,
    RetrievalProfile,
    RetrievalService,
)
from agent_api.settings import PyodideConfig


@dataclass(slots=True)
class ToolRuntime:
    conversation_id: str
    owner_user_id: str | None
    auth: AuthContext
    db_session: AsyncSession
    retrieval: RetrievalService
    request_id: str | None
    pyodide: PyodideConfig
    last_retrieval: RetrievalContext | None = None
    metadata: dict[str, Any] | None = None
    retrieval_profile: RetrievalProfile = RetrievalProfile.DEFAULT
    target_country_code: str | None = None
    hints: dict[str, Any] | None = None


_tool_runtime: contextvars.ContextVar[ToolRuntime | None] = contextvars.ContextVar(
    "tool_runtime", default=None
)


def set_runtime(runtime: ToolRuntime) -> None:
    _tool_runtime.set(runtime)


def get_runtime() -> ToolRuntime:
    runtime = _tool_runtime.get()
    if runtime is None:
        raise RuntimeError("Tool runtime not set")
    return runtime


__all__ = ["ToolRuntime", "get_runtime", "set_runtime"]
