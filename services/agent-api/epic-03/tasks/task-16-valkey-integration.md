# Task 16 — Production Valkey Client & Cache Wiring

## System Snapshot
- Cache keys, serializers, and writer helpers exist (Tasks 05 & 07), and telemetry hooks expect Valkey metrics (Tasks 12–13).
- The only cache client today is `InMemoryValkeyClient`, explicitly documented as a stub; no real Valkey/Redis connection, pooling, TLS, or configuration is present.
- Epic 3’s scope calls for “Valkey cache integration,” but cache hits/misses currently never reach the shared Valkey cluster.

## What You Inherit
- Deterministic cache key helpers + metadata (`cache/cache_keys.py`, `state/agent_state.py`).
- CacheWriter/maybe_serve_from_cache entrypoints ready to accept any `ValkeyCacheClientProtocol` implementation.
- Docs describing Valkey topology, TTLs, and rate-limiter expectations (`docs/overview/system_architecture.md §3.3`, `docs/agents/implementation.md §3.2`).

## Goal
Implement a production-ready Valkey client, configuration, and dependency wiring so cache hits/misses/write-through updates talk to the real Valkey deployment instead of the in-memory stub. Provide integration tests and documentation covering env vars, connection pooling, TLS, and failure handling.

## Must Read Before Coding
1. `docs/epics/03.md` (Valkey requirements across Tasks 3.2–3.5).
2. `docs/overview/system_architecture.md` §3.3 (cache topology, TTL, rate limiting).
3. `docs/agents/implementation.md` §3.2 (CacheWriter usage, cache invalidation).
4. Task 07 & Task 13 summaries (logs under `services/agent-api/logs/task_07` and `task_13`) for telemetry expectations.

## Implementation Scope & Files
- New Valkey client module (e.g., `services/agent-api/src/cache/valkey_async_client.py`) built on `valkey-py` or `redis.asyncio`, implementing `ValkeyCacheClientProtocol` with connection pooling and optional TLS.
- Configuration helpers (`services/agent-api/src/config/cache.py`) to parse env vars: `VALKEY_URL`, `VALKEY_USERNAME`, `VALKEY_PASSWORD`, `VALKEY_DB`, `VALKEY_TLS_CERT`, `VALKEY_MAX_CONNECTIONS`, TTL overrides, etc.
- FastAPI dependency wiring so production routes instantiate the real client, while tests continue using `InMemoryValkeyClient`.
- Integration tests (`services/agent-api/tests/cache/test_valkey_client.py`) that spin up a Valkey/Redis container via Testcontainers, covering get/set/tag_hit/tag_miss along with telemetry side-effects.
- Documentation updates describing deployment requirements and local dev instructions.

## Step-by-Step Instructions
1. **Dependency & config**: Add `valkey-py` (or `redis`) to `pyproject.toml`. Create config helpers (pydantic settings or simple dataclass) reading env vars for host(s), DB, TLS, timeouts, and telemetry sampling. Support Sentinel/cluster URIs if required by architecture doc.
2. **Async client implementation**: Wrap the chosen Valkey library so it satisfies `ValkeyCacheClientProtocol`. Ensure commands are awaited, connection pooling is reused, and tag_hit/tag_miss push telemetry labels (route, reason) via `CacheObservability` when available.
3. **Error handling**: Implement retry/backoff or best-effort logging when Valkey is unavailable. Cache misses should gracefully fall back to live LangGraph execution rather than crashing the request.
4. **Injection**: Update the FastAPI DI container to supply the real client in production paths while keeping the in-memory stub for unit tests. Provide a fixture that yields the stub when `settings.VALKEY_URL` is unset (developer ergonomics).
5. **Testing**: Use Testcontainers (or docker-compose) to boot a Valkey server during pytest. Cover basic CRUD, TTL expiry, error paths, and concurrency (multiple simultaneous get/set). Ensure tests skip gracefully if Docker is unavailable (matching existing repository patterns).
6. **Docs & Runbooks**: Update `docs/overview/system_architecture.md` and `docs/agents/implementation.md` to describe the new env vars, pooling numbers, TLS expectations, and troubleshooting steps. Mention how to run the service locally with a Dockerized Valkey instance.
7. **Rollout plan**: Document how to switch environments from stub to real Valkey (e.g., set `VALKEY_URL` + credentials). Include guidance on migrating existing cache entries or clearing the namespace when schema versions change.

## Definition of Done
- Production Valkey client implemented, configurable via env vars, and injected into CacheWriter/maybe_serve_from_cache for real requests.
- Integration tests validate client behavior against a running Valkey instance.
- Documentation/runbooks updated, and developer instructions exist for running Valkey locally.
- Standard verification commands executed and summarized.

## Handoff Notes
- Capture any TODOs for future scaling (e.g., Sentinel failover, sharding) so SREs know what to prioritize next.
- If rate-limiter hooks depend on Valkey (per docs §3.3), note whether additional work is needed to integrate them once the base client ships.
