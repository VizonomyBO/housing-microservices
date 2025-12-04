"""Prometheus + OpenTelemetry helpers for the agent service.

This module centralizes every observable metric required by Task 13 so LangGraph
nodes, cache helpers, and HITL flows can record telemetry without each component
constructing its own counters. The registry intentionally keeps state light so it
can be shared safely across workers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

_LATENCY_BUCKETS = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)
_RATE_LIMIT_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
)


@dataclass(slots=True)
class _CacheTotals:
    hits: float = 0.0
    misses: float = 0.0

    def ratio(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


@dataclass
class MetricsRegistry:
    """Wraps Prometheus primitives and exposes ergonomic helpers."""

    service_name: str = "agent_api"
    registry: CollectorRegistry | None = None
    tracer_name: str | None = None
    _cache_totals: dict[tuple[str, str | None], _CacheTotals] = field(
        default_factory=lambda: defaultdict(_CacheTotals)
    )
    _registry: CollectorRegistry = field(init=False)
    _tracer: trace.Tracer = field(init=False)

    def __post_init__(self) -> None:
        self._registry = self.registry or CollectorRegistry(auto_describe=True)
        self._tracer = trace.get_tracer(self.tracer_name or f"{self.service_name}.telemetry")

        self.node_latency = Histogram(
            "agent_node_latency_seconds",
            "Latency per LangGraph node/subgraph",
            ("node", "subgraph", "route", "status"),
            buckets=_LATENCY_BUCKETS,
            registry=self._registry,
        )
        self.token_usage = Counter(
            "agent_token_usage_total",
            "Accumulated LLM token usage segmented by direction",
            ("model", "direction", "route"),
            registry=self._registry,
        )
        self.cache_events = Counter(
            "agent_cache_events_total",
            "Cache hits/misses/writes emitted by CacheWriter",
            ("event", "namespace", "route"),
            registry=self._registry,
        )
        self.cache_hit_ratio = Gauge(
            "agent_cache_hit_ratio",
            "Rolling cache hit ratio derived from hits/misses",
            ("namespace", "route"),
            registry=self._registry,
        )
        self.hitl_events = Counter(
            "agent_hitl_events_total",
            "Human-in-the-loop pause/resume counts",
            ("event", "reason", "route"),
            registry=self._registry,
        )
        self.guardrail_violations = Counter(
            "agent_guardrail_violations_total",
            "Guardrail violations grouped by code/severity",
            ("code", "severity"),
            registry=self._registry,
        )
        self.auth_events = Counter(
            "agent_auth_events_total",
            "Authentication success/failure counts grouped by reason",
            ("event", "reason"),
            registry=self._registry,
        )
        self.rate_limiter_wait = Histogram(
            "agent_rate_limiter_wait_seconds",
            "Observed wait durations when requesting limiter permits",
            ("model", "route"),
            buckets=_RATE_LIMIT_BUCKETS,
            registry=self._registry,
        )

    @property
    def prometheus_registry(self) -> CollectorRegistry:
        return self._registry

    def render_prometheus(self) -> bytes:
        """Expose metrics in Prometheus text format so FastAPI can serve them."""

        return generate_latest(self._registry)

    def observe_node_latency(
        self,
        *,
        node: str,
        subgraph: str | None,
        route: str | None,
        status: str,
        duration_seconds: float,
    ) -> None:
        self.node_latency.labels(node, subgraph or "none", route or "none", status).observe(
            duration_seconds
        )

    def record_token_usage(
        self, *, model: str, direction: str, route: str | None, tokens: float
    ) -> None:
        if tokens <= 0:
            return
        self.token_usage.labels(model, direction, route or "none").inc(tokens)

    def record_cache_event(
        self,
        *,
        event: str,
        namespace: str,
        route: str | None,
        latency_seconds: float | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        self.cache_events.labels(event, namespace, route or "none").inc()
        key = (namespace, route or "none")
        if event == "hit":
            self._cache_totals[key].hits += 1
        elif event == "miss":
            self._cache_totals[key].misses += 1
        self.cache_hit_ratio.labels(*key).set(self._cache_totals[key].ratio())
        # The optional latency/ttl parameters are reserved for future histogram wiring.
        _ = latency_seconds, ttl_seconds

    def record_hitl_event(
        self,
        *,
        event: str,
        reason: str | None,
        route: str | None,
    ) -> None:
        self.hitl_events.labels(event, reason or "none", route or "none").inc()

    def record_guardrail_violation(self, *, code: str, severity: str) -> None:
        self.guardrail_violations.labels(code, severity).inc()

    def record_auth_event(self, *, event: str, reason: str | None) -> None:
        self.auth_events.labels(event, reason or "none").inc()

    def record_rate_limiter_wait(
        self, *, model: str, route: str | None, wait_seconds: float
    ) -> None:
        self.rate_limiter_wait.labels(model, route or "none").observe(wait_seconds)

    @contextmanager
    def span(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> Iterator[Span]:
        with self._tracer.start_as_current_span(name, kind=SpanKind.INTERNAL) as span:
            self._set_span_attributes(span, attributes)
            try:
                yield span
            except Exception as exc:  # pragma: no cover - OTel handles failures
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, description=str(exc)))
                raise
            else:
                span.set_status(Status(StatusCode.OK))

    @asynccontextmanager
    async def async_span(
        self, name: str, *, attributes: Mapping[str, Any] | None = None
    ) -> AsyncIterator[Span]:
        with self.span(name, attributes=attributes) as span:
            yield span

    def _set_span_attributes(self, span: Span, attributes: Mapping[str, Any] | None) -> None:
        if attributes is None:
            return
        for key, value in attributes.items():
            span.set_attribute(key, value)


@lru_cache(maxsize=1)
def get_metrics_registry() -> MetricsRegistry:
    """Return the singleton metrics registry used by the service."""

    return MetricsRegistry()


__all__ = ["MetricsRegistry", "get_metrics_registry"]
