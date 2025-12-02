# Task 01 — Reduced Scope Gateway & Text-only Streaming

## System Snapshot
- `services/agent-api` already ships the full LangGraph gateway from Epic 3: `/v1/chat` streams SSE events, CacheWriter talks to Valkey, and Router can branch into numerical/vision/table-heavy paths.
- Shared data models live in `packages/shared_data_layer` and already expose chunk/document tables plus attachment repositories.
- Epic 3.5 forces a “text-only, no-Valkey” safe mode so we can demo tomorrow without tearing out advanced features.

## What You Inherit
- Fully wired FastAPI app (`agent_api/http/app.py`), dependency graph (`agent_api/http/deps.py`), and streaming utilities (`agent_api/http/streaming.py`).
- Cache infrastructure (`cache/cache_writer.py`, `cache/valkey_async_client.py`, `cache/valkey_client.py`) and Router/Subgraph implementations from Epic 3.
- Existing docs describing full-scope behavior (`docs/overview/system_architecture.md`, `docs/interfaces/api_contracts.md`, `docs/agents/implementation.md`).

## Goal
Add a `ReducedScopeSettings` feature flag suite and thread it through the HTTP layer, LangGraph nodes, cache/rate-limit wiring, and SSE telemetry so `/v1/chat` only consumes plain-text chunks, skips Valkey/rate limiting, emits a demo-mode SSE event, and leaves the original code paths dormant (not deleted).

## Must Read Before Coding
1. `docs/epics/035.md` — Task 3.5.1 requirements.
2. `docs/overview/system_architecture.md` §§2–3 — LangGraph gateway, limiter, caching expectations.
3. `docs/data/schema_and_persistence.md` §3 — `documents`/`chunks` tables (focus on `chunk_type`).
4. `docs/interfaces/api_contracts.md` §§1–4 — `/v1/chat` + SSE contract that must stay compatible.
5. `docs/agents/implementation.md` §§3–5 — Router, CacheWriter, SSE emitter hooks.

## Implementation Scope & Files
- Create `services/agent-api/src/agent_api/reduced_scope.py` (flag dataclasses + helpers) and update `agent_api/settings.py` to include `ReducedScopeSettings` + env parsing (e.g., `REDUCED_SCOPE_ENABLED`, `REDUCED_SCOPE_TEXT_ONLY_CHUNKS`, `REDUCED_SCOPE_DISABLE_VALKEY`).
- Update `agent_api/http/app.py` and `agent_api/http/deps.py` to stash the new settings, expose them via dependency, and swap Valkey/RateLimiter singletons for no-op shims when reduced scope is enabled.
- Add `agent_api/http/rate_limit.py` (or similar) with `RateLimiterProtocol`, production stub, and `ReducedScopeRateLimiter` that records headers (`X-RateLimit-Policy: demo-mode`) + SSE metadata (`{"rate_limit_disabled": true}`) instead of enforcing quotas.
- Guard Router + LangGraph nodes: update `nodes/router/router_node.py`, `subgraphs/vision/*`, `subgraphs/numerical/*`, and any attachment/CacheWriter emitters so they short-circuit to informational/analyst-only flows and emit a single `SSEEventType.DEMO_SKIPPED` (new constant in `streaming/events.py`).
- Extend `cache/cache_writer.py`, `cache/valkey_async_client.py`, and `cache/valkey_client.py` with a reduced-scope/in-memory branch that preserves telemetry but never touches a Valkey socket. Document TODO hooks for re-enabling.
- Ensure `agent_api/http/routes/chat.py`, `agent_api/http/streaming.py`, and downstream hydration (`repositories/agent_checkpoint_repository.py`, retrieval repos) filter to `chunk_type == 'text'` when building state, and add SSE metadata when non-text attachments are ignored.
- Update docs: `docs/agents/implementation.md` and `docs/interfaces/api_contracts.md` (SSE note + `Viz-Demo-Mode` headers) to describe flag semantics and how to re-enable Valkey/rate limiting.
- Tests to touch: `tests/http/test_chat_stream.py`, `tests/cache/test_cache_writer.py`, `tests/subgraphs/*` (vision/numerical), and new unit tests for the reduced-scope shims (`tests/http/test_rate_limiter.py` or similar).

## Step-by-Step Instructions
1. **Define ReducedScopeSettings + env flags**:
   - Add a dataclass (or Pydantic model) describing `enabled`, `text_only_chunks`, `disable_valkey`, `emit_demo_events`, and `allowed_chunk_types` defaults. Parse from env in `load_settings()` and store on `Settings` so FastAPI middleware can read it.
2. **Swap cache/limiter dependencies when enabled**:
   - In `agent_api/http/app.py` lifespan, detect reduced scope and instantiate an `InMemoryValkeyClient` + `ReducedScopeRateLimiter`. Propagate `settings.reduced_scope` via `Request.app.state`. Update dependency functions to read the limiter + emit response headers (`X-RateLimit-Policy`, `X-Cache-Mode`).
3. **Short-circuit LangGraph branches**:
   - Update Router + subgraphs to honor `state.reduced_scope_flags` (plumb via state/context). If route would hit numerical/vision/table paths, emit a `demo_mode_skipped` SSE event and transition to informational fallback with a TODO comment referencing the epic. Ensure state hydration + retrieval queries filter `chunk_type='text'` when pulling from shared_data_layer repositories.
4. **Update SSE + docs**:
   - Introduce `SSEEventType.DEMO_MODE_SKIPPED` (or similar) and ensure `build_streaming_response` emits one event whenever a non-text capability is suppressed. Document flag behavior + SSE addition in `docs/agents/implementation.md` and `docs/interfaces/api_contracts.md`, and add regression tests proving `/v1/chat` works with `REDUCED_SCOPE_ENABLED=1` and no Valkey URL.

## Definition of Done
- ReducedScope settings + no-op cache/limiter shims exist and are exercised when `REDUCED_SCOPE_ENABLED=1`.
- `/v1/chat` succeeds with only text chunks, emits the new SSE demo-mode event, and sets headers that describe disabled capabilities.
- Router and LangGraph nodes never enter numerical/vision flows while reduced scope is on; they log/emit “feature temporarily disabled” events instead of deleting code.
- Tests cover reduced-scope cases plus existing happy paths; run `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, and `uv run pytest -n auto`.
- Documentation updated with flag semantics and SSE changes.
- **Handoff Notes**: Execution agent must describe which toggles were added, cite the tests/commands they ran, and summarize any TODO markers future tasks must respect (especially where documents/attachments now filter `chunk_type`).

## Handoff Notes
- Capture the exact env variables + default values introduced for reduced scope so Task 02 can reuse them.
- Note any repositories or LangGraph nodes that still assume Valkey/rate limiting so Task 02 knows where to keep guarding.
- Provide links to the new SSE event implementation and rate limiter shim for the next agent.
