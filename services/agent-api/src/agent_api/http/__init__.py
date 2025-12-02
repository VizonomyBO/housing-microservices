"""HTTP gateway package for the Agent API service."""

from __future__ import annotations

from agent_api.http.app import create_app

__all__ = ["create_app"]
