"""Runtime configuration for the rebuilt Agent API."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(slots=True)
class AuthSettings:
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


@dataclass(slots=True)
class VoyageEmbeddingConfig:
    model: str
    dimensions: int


@dataclass(slots=True)
class PyodideConfig:
    base_url: str | None
    request_timeout_seconds: float
    allowed_packages: tuple[str, ...]


@dataclass(slots=True)
class Settings:
    service_name: str
    stack_profile: str
    service_mode: str
    http_port: int
    database_url: str | None
    ingestion_base_url: str
    ingestion_api_key: str | None
    ingestion_request_timeout_seconds: float
    metrics_namespace: str
    metrics_auth_token: str | None
    metrics_auth_header: str
    metrics_auth_scheme: str
    openai_api_key: str | None
    voyage_api_key: str | None
    openai_chat_model: str
    voyage_embedding: VoyageEmbeddingConfig
    voyage_rerank_model: str
    auth: AuthSettings
    cors_allowed_origins: tuple[str, ...]
    cors_allow_credentials: bool
    pyodide: PyodideConfig


def load_settings() -> Settings:
    openai_api_key = _env_str("OPENAI_API_KEY")
    voyage_api_key = _env_str("VOYAGE_API_KEY")
    _validate_required_secrets(
        {
            "OPENAI_API_KEY": openai_api_key,
            "VOYAGE_API_KEY": voyage_api_key,
        }
    )

    stack_profile = (_env_str("STACK_PROFILE", "prod") or "prod").lower()
    service_mode = (_env_str("SERVICE_MODE", stack_profile) or stack_profile).lower()

    embedding_model = _env_str("VOYAGE_EMBEDDING_MODEL", "voyage-context-3") or "voyage-context-3"
    embedding_dims = _env_int("VOYAGE_EMBEDDING_DIMENSIONS", 1024)
    voyage_embedding = VoyageEmbeddingConfig(model=embedding_model, dimensions=embedding_dims)

    auth_settings = AuthSettings(
        jwks_url=_env_str("AUTH_JWKS_URL"),
        issuer=_env_str("AUTH_JWT_ISSUER"),
        audience=_env_str("AUTH_JWT_AUDIENCE"),
        algorithms=_env_csv("AUTH_JWT_ALGORITHMS", ("RS256", "HS256")),
        cache_ttl_seconds=_env_int("AUTH_JWKS_CACHE_SECONDS", 3600),
        leeway_seconds=_env_int("AUTH_JWT_LEEWAY_SECONDS", 60),
        required_scopes=_env_csv("AUTH_REQUIRED_SCOPES"),
        shared_secret=_env_str("AUTH_SHARED_SECRET") or _env_str("JWT_SECRET_KEY"),
        scope_claim=_env_str("AUTH_SCOPE_CLAIM", "scope") or "scope",
        tenant_claim=_env_str("AUTH_TENANT_CLAIM", "tenant_id"),
        http_timeout_seconds=_env_float("AUTH_JWKS_TIMEOUT_SECONDS", 5.0),
    )

    cors_allowed_origins = _resolve_cors_origins(
        primary="AGENT_API_CORS_ORIGINS",
        fallback="CORS_ORIGINS",
        default=("http://localhost:3000", "http://localhost:5173"),
    )
    cors_allow_credentials = _env_flag("AGENT_API_CORS_ALLOW_CREDENTIALS", True)
    if "*" in cors_allowed_origins and cors_allow_credentials:
        cors_allow_credentials = False

    ingestion_base_url = _env_str("INGEST_BASE_URL")
    if not ingestion_base_url:
        raise RuntimeError("INGEST_BASE_URL is required for ingestion proxying.")

    pyodide = PyodideConfig(
        base_url=_env_str("PYODIDE_BASE_URL"),
        request_timeout_seconds=_env_float("PYODIDE_REQUEST_TIMEOUT_SECONDS", 20.0),
        allowed_packages=_env_csv("PYODIDE_ALLOWED_PACKAGES", ()),
    )

    return Settings(
        service_name=os.getenv("SERVICE_NAME", "agent_api"),
        stack_profile=stack_profile,
        service_mode=service_mode,
        http_port=_env_int("AGENT_API_PORT", 8000),
        database_url=os.getenv("DATABASE_URL"),
        ingestion_base_url=ingestion_base_url,
        ingestion_api_key=_env_str("INGEST_UPLOAD_API_KEY"),
        ingestion_request_timeout_seconds=_env_float("INGEST_REQUEST_TIMEOUT_SECONDS", 30.0),
        metrics_namespace=os.getenv("METRICS_NAMESPACE", "agent-api"),
        metrics_auth_token=os.getenv("METRICS_AUTH_TOKEN"),
        metrics_auth_header=os.getenv("METRICS_AUTH_HEADER", "Authorization"),
        metrics_auth_scheme=os.getenv("METRICS_AUTH_SCHEME", "Bearer"),
        openai_api_key=openai_api_key,
        voyage_api_key=voyage_api_key,
        openai_chat_model=_env_str("OPENAI_CHAT_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        voyage_embedding=voyage_embedding,
        voyage_rerank_model=_env_str("VOYAGE_RERANK_MODEL", "rerank-2.5") or "rerank-2.5",
        auth=auth_settings,
        cors_allowed_origins=cors_allowed_origins,
        cors_allow_credentials=cors_allow_credentials,
        pyodide=pyodide,
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


def _resolve_cors_origins(
    *, primary: str, fallback: str | None = None, default: Iterable[str] | None = None
) -> tuple[str, ...]:
    def _parse(raw_value: str | None) -> tuple[str, ...]:
        if raw_value is None:
            return ()
        values = [segment.strip() for segment in raw_value.split(",") if segment.strip()]
        return tuple(values)

    origins = _parse(os.getenv(primary))
    if not origins and fallback:
        origins = _parse(os.getenv(fallback))
    if origins:
        return origins
    return tuple(default or ())


def _validate_required_secrets(required: dict[str, str | None]) -> None:
    missing = [name for name, value in required.items() if not value]
    if missing:
        joined = ", ".join(sorted(missing))
        raise RuntimeError(f"Missing required secrets: {joined}")


__all__ = ["AuthSettings", "PyodideConfig", "Settings", "VoyageEmbeddingConfig", "load_settings"]
