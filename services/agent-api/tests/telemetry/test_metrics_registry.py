from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import CollectorRegistry

from telemetry.metrics_registry import MetricsRegistry


def _find_sample(metric, *, label_key: str, label_value: str):
    for sample in metric.samples:
        if sample.labels.get(label_key) == label_value:
            return sample
    raise AssertionError(f"No sample for {label_key}={label_value}")


def test_records_latency_and_cache_ratio() -> None:
    registry = CollectorRegistry()
    metrics = MetricsRegistry(registry=registry)

    metrics.observe_node_latency(
        node="router",
        subgraph="control",
        route="informational",
        status="success",
        duration_seconds=0.05,
    )
    metrics.record_cache_event(event="hit", namespace="agent-api", route="informational")
    metrics.record_cache_event(event="miss", namespace="agent-api", route="informational")

    cache_metric = next(iter(metrics.cache_hit_ratio.collect()))
    sample = _find_sample(cache_metric, label_key="route", label_value="informational")
    assert sample.value == pytest.approx(0.5)

    rendered = metrics.render_prometheus()
    assert b"agent_node_latency_seconds" in rendered
    assert b"agent_cache_events_total" in rendered


def test_span_context_records_attributes() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    previous_provider = trace.get_tracer_provider()
    trace.set_tracer_provider(provider)
    try:
        metrics = MetricsRegistry(registry=CollectorRegistry())
        with metrics.span("langgraph.router", attributes={"agent.node": "router"}):
            pass
    finally:
        trace.set_tracer_provider(previous_provider)
    spans = exporter.get_finished_spans()
    assert spans, "Expected one span to be recorded"
    assert spans[0].attributes["agent.node"] == "router"
