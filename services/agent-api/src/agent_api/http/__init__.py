"""HTTP gateway package for the Agent API service."""

from __future__ import annotations

__all__ = ["create_app"]


def create_app():  # pragma: no cover - thin proxy
    from agent_api.http.app import create_app as _create_app

    return _create_app()
