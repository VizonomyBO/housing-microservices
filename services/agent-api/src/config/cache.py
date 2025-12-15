"""Cache/Valkey configuration helpers + env parsing."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_TTL_SECONDS = 60 * 60 * 48  # 48 hours per architecture doc


class ValkeyTlsSettings(BaseModel):
    """TLS material used when establishing Valkey connections."""

    ca_cert: str | None = Field(default=None, description="CA certificate path or inline PEM")
    client_cert: str | None = Field(
        default=None, description="Client certificate path or inline PEM for mutual TLS"
    )
    client_key: str | None = Field(
        default=None, description="Client private key path or inline PEM for mutual TLS"
    )
    skip_hostname_verification: bool = Field(
        default=False,
        description="Disable hostname verification (not recommended outside local dev)",
    )

    @property
    def enabled(self) -> bool:
        return any([self.ca_cert, self.client_cert, self.client_key])


class ValkeySettings(BaseModel):
    """Runtime configuration for the production Valkey client."""

    url: str | None = Field(default=None, description="redis:// / valkey:// / sentinel:// URI")
    username: str | None = Field(default=None)
    password: str | None = Field(default=None)
    db: int | None = Field(default=None, ge=0)
    max_connections: int = Field(default=64, ge=1)
    socket_timeout_seconds: float = Field(default=3.0, gt=0)
    connect_timeout_seconds: float = Field(default=1.0, gt=0)
    health_check_interval_seconds: float = Field(default=30.0, gt=0)
    pool_idle_timeout_seconds: float | None = Field(default=60.0, ge=0)
    retry_attempts: int = Field(default=3, ge=1)
    retry_backoff_seconds: float = Field(default=0.05, gt=0)
    retry_backoff_multiplier: float = Field(default=2.0, gt=1)
    retry_max_backoff_seconds: float = Field(default=0.5, gt=0)
    retry_jitter_seconds: float = Field(default=0.01, ge=0)
    default_ttl_seconds: int = Field(default=DEFAULT_TTL_SECONDS, ge=1)
    sentinel_service: str | None = Field(default=None)
    cluster_mode: bool = Field(default=False)
    client_name: str = Field(default="agent-api")
    tls: ValkeyTlsSettings = Field(default_factory=ValkeyTlsSettings)

    @property
    def enabled(self) -> bool:
        return bool(self.url)


def _read_secret(path: str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path)
    if not resolved.exists():  # pragma: no cover - defensive
        return None
    return resolved.read_text(encoding="utf-8").strip()


def _get(env: Mapping[str, str], key: str, default: str | None = None) -> str | None:
    value = env.get(key)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _get_bool(env: Mapping[str, str], key: str, default: bool = False) -> bool:
    raw = _get(env, key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _get_int(env: Mapping[str, str], key: str) -> int | None:
    raw = _get(env, key)
    if raw is None:
        return None
    return int(raw)


def _get_float(env: Mapping[str, str], key: str) -> float | None:
    raw = _get(env, key)
    if raw is None:
        return None
    return float(raw)


def load_valkey_settings(env: Mapping[str, str] | None = None) -> ValkeySettings:
    """Hydrate Valkey settings from environment variables (validated via Pydantic)."""

    env_map = env or os.environ
    password = _get(env_map, "VALKEY_PASSWORD")
    password_file = _get(env_map, "VALKEY_PASSWORD_FILE")
    if not password and password_file:
        password = _read_secret(password_file)

    overrides: dict[str, Any] = {
        "cluster_mode": _get_bool(env_map, "VALKEY_CLUSTER_MODE", False),
        "client_name": _get(env_map, "VALKEY_CLIENT_NAME", "agent-api"),
        "tls": {
            "ca_cert": _get(env_map, "VALKEY_TLS_CA_CERT"),
            "client_cert": _get(env_map, "VALKEY_TLS_CLIENT_CERT"),
            "client_key": _get(env_map, "VALKEY_TLS_CLIENT_KEY"),
            "skip_hostname_verification": _get_bool(env_map, "VALKEY_TLS_SKIP_VERIFY", False),
        },
    }

    def _maybe_set(key: str, value: Any | None) -> None:
        if value is not None and value != "":
            overrides[key] = value

    _maybe_set("url", _get(env_map, "VALKEY_URL"))
    _maybe_set("username", _get(env_map, "VALKEY_USERNAME"))
    if password:
        overrides["password"] = password
    _maybe_set("db", _get_int(env_map, "VALKEY_DB"))
    _maybe_set("max_connections", _get_int(env_map, "VALKEY_MAX_CONNECTIONS"))
    _maybe_set("socket_timeout_seconds", _get_float(env_map, "VALKEY_SOCKET_TIMEOUT_SECONDS"))
    _maybe_set("connect_timeout_seconds", _get_float(env_map, "VALKEY_CONNECT_TIMEOUT_SECONDS"))
    _maybe_set(
        "health_check_interval_seconds",
        _get_float(env_map, "VALKEY_HEALTHCHECK_INTERVAL_SECONDS"),
    )
    _maybe_set(
        "pool_idle_timeout_seconds",
        _get_float(env_map, "VALKEY_POOL_IDLE_TIMEOUT_SECONDS"),
    )
    _maybe_set("retry_attempts", _get_int(env_map, "VALKEY_RETRY_ATTEMPTS"))
    _maybe_set("retry_backoff_seconds", _get_float(env_map, "VALKEY_RETRY_BACKOFF_SECONDS"))
    _maybe_set(
        "retry_backoff_multiplier",
        _get_float(env_map, "VALKEY_RETRY_BACKOFF_MULTIPLIER"),
    )
    _maybe_set(
        "retry_max_backoff_seconds",
        _get_float(env_map, "VALKEY_RETRY_MAX_BACKOFF_SECONDS"),
    )
    _maybe_set("retry_jitter_seconds", _get_float(env_map, "VALKEY_RETRY_JITTER_SECONDS"))
    _maybe_set("default_ttl_seconds", _get_int(env_map, "VALKEY_DEFAULT_TTL_SECONDS"))
    _maybe_set("sentinel_service", _get(env_map, "VALKEY_SENTINEL_SERVICE"))

    return ValkeySettings(**overrides)


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "ValkeySettings",
    "ValkeyTlsSettings",
    "load_valkey_settings",
]
