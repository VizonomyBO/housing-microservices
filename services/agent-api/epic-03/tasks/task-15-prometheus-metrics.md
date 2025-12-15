# Task 15 — Metrics Endpoint & Telemetry Bootstrap

## System Snapshot
- Metrics/telemetry helpers (`telemetry/metrics_registry.py`, `telemetry/cache_observability.py`) exist from Task 13, and LangGraph nodes already emit metric references via `lifecycle_span()` + SSE payloads.
- No FastAPI route exposes the Prometheus text output, nor is `MetricsRegistry` registered in the application startup so counters persist across requests.
- CacheWriter/maybe_serve_from_cache accept `CacheObservability`, but the actual HTTP layer never instantiates or injects it, and there is no link to the shared data layer session in production.

## What You Inherit
- Instrumented nodes, SSE events carrying `metric_refs`, and unit tests that prove the registry/observability helpers work in isolation.
- Docs describing required dashboards and database writers (`docs/agents/implementation.md §3.6.2`, `docs/overview/system_architecture.md §3.5`, `docs/data/schema_and_persistence.md §3.7`).
- The FastAPI skeleton from Task 14 (or create both tasks in parallel if needed).

## Goal
Wire the telemetry stack into the actual service lifecycle: instantiate `MetricsRegistry` and `CacheObservability` exactly once per process, inject them wherever needed, expose `/metrics` for Prometheus scraping, and ensure cache/HITL telemetry writes land in the shared data layer.

## Must Read Before Coding
1. `docs/agents/implementation.md` §3.6.2 (metrics + cache observability expectations).
2. `docs/overview/system_architecture.md` §3.5 (dashboard + `/metrics` guidance).
3. `docs/data/schema_and_persistence.md` §3.7–3.8 (tables touched by CacheObservability).
4. Task 13 log summary under `services/agent-api/logs/task_13/codex.log` for explicit TODOs (lines 80870–80905).

## Implementation Scope & Files
- Application bootstrap (`services/agent-api/src/agent_api/http/app.py` or equivalent) to create/load `MetricsRegistry`, `CacheObservability`, and DB session factories.
- Dependency modules (e.g., `services/agent-api/src/agent_api/http/deps.py`) that inject metrics/observability into CacheWriter, HumanGateService, Router, etc.
- New `/metrics` route module (`services/agent-api/src/agent_api/http/routes/metrics.py`) returning `MetricsRegistry.render_prometheus()` with proper headers/auth guards.
- Telemetry wiring in cache/HITL code paths to ensure DB writes receive an `AsyncSession` (`services/agent-api/src/cache/cache_writer.py`, `services/agent-api/src/hitl/human_gate_service.py`, `services/agent-api/src/streaming/with_sse.py`).
- Tests under `services/agent-api/tests/http/test_metrics_route.py` and/or `tests/telemetry/test_prometheus_endpoint.py` verifying Prometheus output, auth, and error handling.

## Step-by-Step Instructions
1. **Singleton metrics registry**: Instantiate `MetricsRegistry` during FastAPI startup (lifespan handler). Store it on `app.state` and provide dependency helpers so routes/nodes share the same counters rather than recreating per request.
2. **Cache observability wiring**: Build a `CacheObservability` instance that references both the metrics registry and shared data layer repositories. Inject it into CacheWriter/maybe_serve_from_cache when constructing LangGraph dependencies so cache hits/misses and writes automatically update Prometheus + Postgres.
3. **Database sessions**: Ensure cache write observability receives an `AsyncSession` sourced from the shared data layer engine (reuse fixtures from Task 02). Prefer `async_sessionmaker` with lifespan-managed engine creation.
4. **/metrics route**: Add a GET endpoint (`/metrics`) that serializes the registry via `render_prometheus()`, sets `Content-Type: text/plain; version=0.0.4`, and enforces whatever auth header the gateway expects (e.g., service token). Document how to disable buffering for scraping.
5. **Routing integration**: Update the SSE gateway (Task 14) so every LangGraph invocation receives references to the singleton metrics/observability helpers (e.g., pass them when constructing CacheWriter, Router, HumanGateService). Confirm `metric_refs` align with the Prometheus series names.
6. **Testing**: Write HTTP-level tests that hit `/metrics` and assert key counters exist (`agent_node_latency_seconds`, `agent_cache_events_total`, etc.). Add telemetry integration tests (can reuse existing fixtures) proving cache hits/misses call into `CacheObservability` when the HTTP layer provides DB sessions.
7. **Docs**: Update `docs/agents/implementation.md` and `docs/overview/system_architecture.md` with the actual module paths/config flags (`METRICS_AUTH_TOKEN`, scraping interval, etc.).

## Definition of Done
- FastAPI `/metrics` endpoint implemented, gated, and documented.
- Metrics registry + cache observability instantiated once per process and injected into LangGraph dependencies.
- CacheWriter/HumanGate/Router record Prometheus counters and Postgres telemetry during real requests (verified via tests or integration harness).
- Standard verification commands executed and summarized.

## Handoff Notes
- Document environment variables or config settings (e.g., `METRICS_AUTH_TOKEN`, DB DSN) so deployment owners can wire secrets.
- Capture any follow-up needed for distributed tracing exporters (OTel) so future tasks can enable Jaeger/Tempo without revisiting the registry glue.
