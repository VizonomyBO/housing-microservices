"""Helpers for building AWS/LocalStack clients based on repo-wide toggles."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from boto3.session import Session


@dataclass(frozen=True)
class AWSRuntimeConfig:
    """Resolved AWS client configuration derived from environment variables."""

    use_localstack: bool
    region: str
    endpoint_url: str | None
    access_key_id: str | None
    secret_access_key: str | None
    host: str
    edge_port: int


_FLAG_TRUE = {"1", "true", "yes", "on"}


def load_runtime_config() -> AWSRuntimeConfig:
    """Load AWS-related settings while honoring the LocalStack toggle."""

    use_localstack = _flag(os.getenv("USE_LOCALSTACK"), default=True)
    host = _str(os.getenv("LOCALSTACK_HOST"), default="localstack")
    edge_port = _int(os.getenv("LOCALSTACK_EDGE_PORT"), default=4566)
    explicit_endpoint = _optional_str(os.getenv("AWS_ENDPOINT_URL"))
    endpoint_url = _derive_endpoint(explicit_endpoint, use_localstack, host, edge_port)

    return AWSRuntimeConfig(
        use_localstack=use_localstack,
        region=_str(os.getenv("AWS_REGION"), default="us-east-1"),
        endpoint_url=endpoint_url,
        access_key_id=_optional_str(os.getenv("AWS_ACCESS_KEY_ID")) or _default_access_key(
            use_localstack
        ),
        secret_access_key=
            _optional_str(os.getenv("AWS_SECRET_ACCESS_KEY"))
            or _default_secret_key(use_localstack),
        host=host,
        edge_port=edge_port,
    )


def describe_runtime(config: AWSRuntimeConfig) -> str:
    """Return a human-readable summary for logging."""

    target = config.endpoint_url or "aws"
    mode = "localstack" if config.use_localstack else "aws"
    return f"mode={mode} endpoint={target} region={config.region}"


def build_client(service: str, *, runtime: AWSRuntimeConfig | None = None, **client_kwargs: Any):
    """Instantiate a boto3 client using the resolved runtime configuration."""

    runtime = runtime or load_runtime_config()
    session = Session(
        aws_access_key_id=runtime.access_key_id,
        aws_secret_access_key=runtime.secret_access_key,
        region_name=runtime.region,
    )

    if runtime.endpoint_url:
        client_kwargs.setdefault("endpoint_url", runtime.endpoint_url)

    return session.client(service, **client_kwargs)


def _derive_endpoint(
    explicit: str | None,
    use_localstack: bool,
    host: str,
    edge_port: int,
) -> str | None:
    if explicit:
        return explicit
    if use_localstack:
        return f"http://{host}:{edge_port}"
    return None


def _flag(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in _FLAG_TRUE


def _str(raw: str | None, *, default: str) -> str:
    if raw is None:
        return default
    raw = raw.strip()
    return raw or default


def _optional_str(raw: str | None) -> str | None:
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _int(raw: str | None, *, default: int) -> int:
    if raw is None:
        return default
    raw = raw.strip()
    return int(raw) if raw else default


def _default_access_key(use_localstack: bool) -> str | None:
    return "localstack" if use_localstack else None


def _default_secret_key(use_localstack: bool) -> str | None:
    return "localstack" if use_localstack else None


__all__ = [
    "AWSRuntimeConfig",
    "build_client",
    "describe_runtime",
    "load_runtime_config",
]
