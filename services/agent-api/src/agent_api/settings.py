"""Service settings + environment helpers for the Agent API."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

from agent_api.reduced_scope import ReducedScopeSettings, coerce_allowed_chunk_types
from config import ValkeySettings, load_valkey_settings


@dataclass(slots=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    service_name: str
    stack_profile: str
    service_mode: str
    http_port: int
    database_url: str | None
    use_localstack: bool
    localstack_host: str
    localstack_edge_port: int
    aws_region: str
    aws_endpoint_url: str | None
    aws_access_key_id: str | None
    aws_secret_access_key: str | None
    metrics_namespace: str
    metrics_auth_token: str | None
    metrics_auth_header: str
    metrics_auth_scheme: str
    valkey_settings: ValkeySettings
    reduced_scope: ReducedScopeSettings
    openai_api_key: str | None
    voyage_api_key: str | None
    openai_chat_model: str
    voyage_embedding_model: str
    auth: AuthSettings


@dataclass(slots=True)
class AuthSettings:
    """Configuration required to validate JWTs issued by auth-service."""

    jwks_url: str | None
    issuer: str | None
    audience: str | None
    algorithms: tuple[str, ...]
    cache_ttl_seconds: int
    leeway_seconds: int
    required_scopes: tuple[str, ...]
    shared_secret: str | None
    scope_claim: str
    tenant_claim: str | None
    http_timeout_seconds: float


def load_settings() -> Settings:
    """Load settings from environment variables with safe defaults."""

    reduced_scope = ReducedScopeSettings(
        enabled=_env_flag("REDUCED_SCOPE_ENABLED", default=False),
        use_real_tools=_env_flag("REDUCED_SCOPE_USE_REAL_TOOLS", default=False),
        text_only_chunks=_env_flag("REDUCED_SCOPE_TEXT_ONLY_CHUNKS", default=True),
        disable_valkey=_env_flag("REDUCED_SCOPE_DISABLE_VALKEY", default=True),
        disable_rate_limiting=_env_flag("REDUCED_SCOPE_DISABLE_RATE_LIMITING", default=True),
        emit_demo_events=_env_flag("REDUCED_SCOPE_EMIT_DEMO_EVENTS", default=True),
        allowed_chunk_types=coerce_allowed_chunk_types(
            os.getenv("REDUCED_SCOPE_ALLOWED_CHUNK_TYPES")
        ),
    )

    openai_api_key = _env_str("OPENAI_API_KEY")
    voyage_api_key = _env_str("VOYAGE_API_KEY")
    openai_chat_model = _env_str("OPENAI_CHAT_MODEL", default="gpt-4o-mini") or "gpt-4o-mini"
    voyage_embedding_model = (
        _env_str("VOYAGE_EMBEDDING_MODEL", default="voyage-3-lite") or "voyage-3-lite"
    )

    _validate_real_tooling_requirements(
        reduced_scope=reduced_scope,
        required_secrets={
            "OPENAI_API_KEY": openai_api_key,
            "VOYAGE_API_KEY": voyage_api_key,
        },
    )

    stack_profile = (_env_str("STACK_PROFILE", default="reduced") or "reduced").lower()
    service_mode = (_env_str("SERVICE_MODE", default=stack_profile) or stack_profile).lower()

    localstack_host = _env_str("LOCALSTACK_HOST", default="localstack") or "localstack"
    localstack_edge_port = _env_int("LOCALSTACK_EDGE_PORT", default=4566)
    use_localstack = _env_flag("USE_LOCALSTACK", default=True)

    auth_settings = AuthSettings(
        jwks_url=_env_str("AUTH_JWKS_URL"),
        issuer=_env_str("AUTH_JWT_ISSUER"),
        audience=_env_str("AUTH_JWT_AUDIENCE"),
        algorithms=_env_csv(
            "AUTH_JWT_ALGORITHMS",
            default=("RS256", "HS256"),
        ),
        cache_ttl_seconds=_env_int("AUTH_JWKS_CACHE_SECONDS", default=3600),
        leeway_seconds=_env_int("AUTH_JWT_LEEWAY_SECONDS", default=60),
        required_scopes=_env_csv("AUTH_REQUIRED_SCOPES"),
        shared_secret=_env_str("AUTH_SHARED_SECRET") or _env_str("JWT_SECRET_KEY"),
        scope_claim=_env_str("AUTH_SCOPE_CLAIM", default="scope") or "scope",
        tenant_claim=_env_str("AUTH_TENANT_CLAIM", default="tenant_id"),
        http_timeout_seconds=_env_float("AUTH_JWKS_TIMEOUT_SECONDS", default=5.0),
    )

    return Settings(
        service_name=os.getenv("SERVICE_NAME", "agent_api"),
        stack_profile=stack_profile,
        service_mode=service_mode,
        http_port=_env_int("AGENT_API_PORT", default=8000),
        database_url=os.getenv("DATABASE_URL"),
        use_localstack=use_localstack,
        localstack_host=localstack_host,
        localstack_edge_port=localstack_edge_port,
        aws_region=_env_str("AWS_REGION", default="us-east-1") or "us-east-1",
        aws_endpoint_url=_resolve_aws_endpoint_url(
            explicit=_env_str("AWS_ENDPOINT_URL"),
            use_localstack=use_localstack,
            host=localstack_host,
            edge_port=localstack_edge_port,
        ),
        aws_access_key_id=_coalesce_localstack_default(
            _env_str("AWS_ACCESS_KEY_ID"), use_localstack=use_localstack
        ),
        aws_secret_access_key=_coalesce_localstack_default(
            _env_str("AWS_SECRET_ACCESS_KEY"), use_localstack=use_localstack
        ),
        metrics_namespace=os.getenv("METRICS_NAMESPACE", "agent-api"),
        metrics_auth_token=os.getenv("METRICS_AUTH_TOKEN"),
        metrics_auth_header=os.getenv("METRICS_AUTH_HEADER", "Authorization"),
        metrics_auth_scheme=os.getenv("METRICS_AUTH_SCHEME", "Bearer"),
        valkey_settings=load_valkey_settings(),
        reduced_scope=reduced_scope,
        openai_api_key=openai_api_key,
        voyage_api_key=voyage_api_key,
        openai_chat_model=openai_chat_model,
        voyage_embedding_model=voyage_embedding_model,
        auth=auth_settings,
    )


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    return int(raw) if raw else default


def _env_str(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value or default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    return float(raw) if raw else default


def _env_csv(name: str, default: Iterable[str] | None = None) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return tuple(default or ())
    values = [segment.strip() for segment in raw.split(",") if segment.strip()]
    if not values and default is not None:
        return tuple(default)
    return tuple(values)


def _resolve_aws_endpoint_url(
    *, explicit: str | None, use_localstack: bool, host: str, edge_port: int
) -> str | None:
    if explicit:
        return explicit
    if use_localstack:
        return f"http://{host}:{edge_port}"
    return None


def _coalesce_localstack_default(value: str | None, *, use_localstack: bool) -> str | None:
    if value:
        return value
    if use_localstack:
        return "localstack"
    return None


def _validate_real_tooling_requirements(
    *, reduced_scope: ReducedScopeSettings, required_secrets: dict[str, str | None]
) -> None:
    if not reduced_scope.use_real_tools:
        return
    missing = [name for name, value in required_secrets.items() if not value]
    if missing:
        joined = ", ".join(sorted(missing))
        raise RuntimeError(
            "Real tooling mode requested (REDUCED_SCOPE_USE_REAL_TOOLS=1) but missing secrets: "
            f"{joined}. Update your environment (.env/.env.local) before rerunning."
        )


__all__ = ["AuthSettings", "Settings", "load_settings"]
