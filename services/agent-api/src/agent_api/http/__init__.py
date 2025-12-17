"""HTTP gateway package for the Agent API service."""

from agent_api.http.app import create_app

__all__ = ["create_app"]
