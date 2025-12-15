"""Production Valkey client built on top of valkey.asyncio."""

from __future__ import annotations

import asyncio
import logging
import random
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from valkey import asyncio as valkey_async
from valkey.asyncio.client import Valkey as AsyncValkey
from valkey.asyncio.cluster import ValkeyCluster
from valkey.asyncio.sentinel import Sentinel as AsyncSentinel
from valkey.exceptions import (
    BusyLoadingError,
)
from valkey.exceptions import (
    ConnectionError as ValkeyConnectionError,
)
from valkey.exceptions import (
    TimeoutError as ValkeyTimeoutError,
)

from cache.valkey_client import ValkeyCacheClientProtocol
from config import ValkeySettings

if TYPE_CHECKING:
    from telemetry import CacheObservability

logger = logging.getLogger(__name__)

_RETRYABLE_ERRORS = (ValkeyConnectionError, ValkeyTimeoutError, BusyLoadingError)
_DEFAULT_NAMESPACE_SUFFIX = "valkey-client"
ValkeyClient = AsyncValkey | ValkeyCluster


@dataclass(slots=True)
class ValkeyAsyncClient(ValkeyCacheClientProtocol):
    """Async Valkey client that satisfies the cache protocol with pooling + retries."""

    settings: ValkeySettings
    _client: ValkeyClient
    observability: CacheObservability | None = None
    namespace_suffix: str = field(default=_DEFAULT_NAMESPACE_SUFFIX)
    _closed: bool = field(default=False, init=False)

    @classmethod
    def from_settings(
        cls,
        settings: ValkeySettings,
        *,
        observability: CacheObservability | None = None,
    ) -> ValkeyAsyncClient:
        if not settings.enabled:
            raise ValueError("VALKEY_URL is not configured; cannot build ValkeyAsyncClient")
        client = _build_valkey_client(settings)
        return cls(settings=settings, _client=client, observability=observability)

    async def close(self) -> None:
        if self._closed:
            return
        await self._client.aclose()
        self._closed = True

    async def get(self, key: str) -> bytes | None:
        result = await self._with_retries(lambda client: client.get(key), operation="get")
        return result

    async def set(
        self,
        key: str,
        value: bytes | str,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        payload = value if isinstance(value, bytes) else value.encode("utf-8")
        ttl = ttl_seconds if ttl_seconds is not None else self.settings.default_ttl_seconds
        await self._with_retries(
            lambda client: client.set(key, payload, ex=ttl if ttl else None),
            operation="set",
        )

    async def delete(self, key: str) -> None:
        await self._with_retries(lambda client: client.delete(key), operation="delete")

    async def tag_hit(self, key: str) -> None:
        self._emit_event("hit")

    async def tag_miss(self, key: str, *, reason: str | None = None) -> None:
        if reason:
            logger.debug("Valkey miss recorded for key=%s reason=%s", key, reason)
        self._emit_event("miss")

    async def _with_retries(
        self,
        func: Callable[[ValkeyClient], Awaitable[Any]],
        *,
        operation: str,
    ) -> Any:
        attempt = 0
        delay = self.settings.retry_backoff_seconds
        while True:
            try:
                return await func(self._client)
            except _RETRYABLE_ERRORS as exc:
                attempt += 1
                if attempt >= self.settings.retry_attempts:
                    logger.warning(
                        "Valkey %s failed after %s attempts: %s", operation, attempt, exc
                    )
                    raise
                sleep_for = min(delay, self.settings.retry_max_backoff_seconds)
                sleep_for += random.uniform(0, self.settings.retry_jitter_seconds)
                logger.debug(
                    "Valkey %s retry %s (sleep %.3fs): %s", operation, attempt, sleep_for, exc
                )
                await asyncio.sleep(sleep_for)
                delay *= self.settings.retry_backoff_multiplier
            except Exception:
                raise

    def _emit_event(self, event: str) -> None:
        if self.observability is None:
            return
        namespace = f"{self.settings.client_name}:{self.namespace_suffix}"
        self.observability.metrics.record_cache_event(
            event=event,
            namespace=namespace,
            route=None,
        )


def _build_valkey_client(settings: ValkeySettings) -> ValkeyClient:
    if settings.url is None:
        raise ValueError("VALKEY_URL must be configured when enabling Valkey")
    conn_kwargs = _connection_kwargs(settings)
    ssl_kwargs = _ssl_kwargs(settings)
    if settings.sentinel_service:
        sentinels, default_db = _parse_sentinel_endpoints(settings.url)
        sentinel_client = AsyncSentinel(
            sentinels,
            sentinel_kwargs=ssl_kwargs,
            **conn_kwargs,
        )
        db = settings.db if settings.db is not None else default_db
        return sentinel_client.master_for(
            service_name=settings.sentinel_service,
            db=db,
            username=settings.username,
            password=settings.password,
            **conn_kwargs,
            **ssl_kwargs,
        )

    if settings.cluster_mode:
        return valkey_async.RedisCluster.from_url(
            settings.url,
            **conn_kwargs,
            **ssl_kwargs,
            username=settings.username,
            password=settings.password,
        )

    return valkey_async.from_url(
        settings.url,
        **conn_kwargs,
        **ssl_kwargs,
        username=settings.username,
        password=settings.password,
        db=settings.db,
    )


def _connection_kwargs(settings: ValkeySettings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "socket_timeout": settings.socket_timeout_seconds,
        "socket_connect_timeout": settings.connect_timeout_seconds,
        "health_check_interval": settings.health_check_interval_seconds,
        "max_connections": settings.max_connections,
        "retry_on_timeout": True,
        "client_name": settings.client_name,
    }
    return kwargs


def _ssl_kwargs(settings: ValkeySettings) -> dict[str, Any]:
    tls = settings.tls
    url = settings.url or ""
    requires_tls = tls.enabled or url.startswith(("valkeys://", "rediss://"))
    if not requires_tls:
        return {}
    kwargs: dict[str, Any] = {"ssl": True}
    if tls.ca_cert:
        kwargs["ssl_ca_certs"] = tls.ca_cert
    if tls.client_cert:
        kwargs["ssl_certfile"] = tls.client_cert
    if tls.client_key:
        kwargs["ssl_keyfile"] = tls.client_key
    if tls.skip_hostname_verification:
        kwargs["ssl_cert_reqs"] = ssl.CERT_NONE
        kwargs["ssl_check_hostname"] = False
    return kwargs


def _parse_sentinel_endpoints(url: str | None) -> tuple[list[tuple[str, int]], int]:
    if not url:
        raise ValueError("Sentinel mode requires VALKEY_URL with sentinel endpoints")
    parsed = urlparse(url)
    if parsed.scheme != "sentinel":
        raise ValueError("Sentinel settings require sentinel:// URL")
    hosts = parsed.netloc.split(",")
    endpoints: list[tuple[str, int]] = []
    for host in hosts:
        if not host:
            continue
        if ":" in host:
            hostname, port = host.split(":", 1)
        else:
            hostname, port = host, "26379"
        endpoints.append((hostname, int(port)))
    db = int(parsed.path.strip("/") or "0") if parsed.path else 0
    return endpoints, db


__all__ = ["ValkeyAsyncClient"]
