"""Service settings + environment helpers for the Agent API."""

from __future__ import annotations

import os
from dataclasses import dataclass

from config import ValkeySettings, load_valkey_settings


@dataclass(slots=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    service_name: str
    database_url: str | None
    metrics_namespace: str
    metrics_auth_token: str | None
    metrics_auth_header: str
    metrics_auth_scheme: str
    valkey_settings: ValkeySettings


def load_settings() -> Settings:
    """Load settings from environment variables with safe defaults."""

    return Settings(
        service_name=os.getenv("SERVICE_NAME", "agent_api"),
        database_url=os.getenv("DATABASE_URL"),
        metrics_namespace=os.getenv("METRICS_NAMESPACE", "agent-api"),
        metrics_auth_token=os.getenv("METRICS_AUTH_TOKEN"),
        metrics_auth_header=os.getenv("METRICS_AUTH_HEADER", "Authorization"),
        metrics_auth_scheme=os.getenv("METRICS_AUTH_SCHEME", "Bearer"),
        valkey_settings=load_valkey_settings(),
    )


__all__ = ["Settings", "load_settings"]
