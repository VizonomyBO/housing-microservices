"""Service settings + environment helpers for the Agent API."""

from __future__ import annotations

import os
from dataclasses import dataclass

from agent_api.reduced_scope import ReducedScopeSettings, coerce_allowed_chunk_types
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
    reduced_scope: ReducedScopeSettings


def load_settings() -> Settings:
    """Load settings from environment variables with safe defaults."""

    reduced_scope = ReducedScopeSettings(
        enabled=_env_flag("REDUCED_SCOPE_ENABLED", default=False),
        text_only_chunks=_env_flag("REDUCED_SCOPE_TEXT_ONLY_CHUNKS", default=True),
        disable_valkey=_env_flag("REDUCED_SCOPE_DISABLE_VALKEY", default=True),
        disable_rate_limiting=_env_flag("REDUCED_SCOPE_DISABLE_RATE_LIMITING", default=True),
        emit_demo_events=_env_flag("REDUCED_SCOPE_EMIT_DEMO_EVENTS", default=True),
        allowed_chunk_types=coerce_allowed_chunk_types(
            os.getenv("REDUCED_SCOPE_ALLOWED_CHUNK_TYPES")
        ),
    )

    return Settings(
        service_name=os.getenv("SERVICE_NAME", "agent_api"),
        database_url=os.getenv("DATABASE_URL"),
        metrics_namespace=os.getenv("METRICS_NAMESPACE", "agent-api"),
        metrics_auth_token=os.getenv("METRICS_AUTH_TOKEN"),
        metrics_auth_header=os.getenv("METRICS_AUTH_HEADER", "Authorization"),
        metrics_auth_scheme=os.getenv("METRICS_AUTH_SCHEME", "Bearer"),
        valkey_settings=load_valkey_settings(),
        reduced_scope=reduced_scope,
    )


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


__all__ = ["Settings", "load_settings"]
