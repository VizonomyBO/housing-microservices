# Task 14 — Streaming Gateway & SSE Proxy

## System Snapshot
- All LangGraph nodes are instrumented with SSE lifecycle helpers (Task 12), but no HTTP entrypoint consumes `SSEEmitter` yet.
- Clients expect the streaming flavor of `POST /v1/chat` documented in `docs/interfaces/api_contracts.md`, yet the service currently lacks a FastAPI app/router.
- Telemetry decorators already emit events/metric refs once an emitter exists, so the remaining work is wiring the emitter into the HTTP surface.

## What You Inherit
- `services/agent-api/src/streaming/{events.py,sse_emitter.py,with_sse.py}` implement the runtime contracts (+ queue loop, keep-alive comments, lifecycle spans).
- CacheWriter, HumanGate, and subgraph nodes all accept optional `sse_emitter` hooks, so you only need to provide the emitter via dependency injection.
- Docs describing the API + SSE envelopes live in `docs/interfaces/api_contracts.md §1.3` and `docs/agents/implementation.md §3.6`.

## Goal
Expose a FastAPI streaming endpoint for `POST /v1/chat` (and any supporting dependency scaffolding) that instantiates `SSEEmitter`, forwards LangGraph events to the client as Server-Sent Events, and tears down cleanly when the graph finishes or errors.

## Must Read Before Coding
1. `docs/interfaces/api_contracts.md` §1.3 (chat streaming contract + SSE frame shapes).
2. `docs/agents/implementation.md` §3.6 (Task 12 streaming narrative) and §4 (LangGraph orchestration overview).
3. `docs/overview/system_architecture.md` §3.4 (Gateway expectations, keep-alives, auth headers).
4. `services/agent-api/AGENTS.md` (workflow + verification commands).

## Implementation Scope & Files
- Introduce a FastAPI application (e.g., `services/agent-api/src/agent_api/http/app.py`) plus routers under `services/agent-api/src/agent_api/http/routes/chat.py`.
- Dependency helpers & request models (e.g., `services/agent-api/src/agent_api/http/deps.py`, `services/agent-api/src/agent_api/http/schemas.py`).
- Streaming orchestration glue (e.g., `services/agent-api/src/agent_api/http/streaming.py`) that takes a validated chat request, instantiates `SSEEmitter`, invokes the LangGraph runner, and turns the emitter iterator into an `EventSourceResponse`/`StreamingResponse`.
- Tests under `services/agent-api/tests/http/test_chat_stream.py` that mock the LangGraph runner and assert SSE formatting, keep-alives, and error propagation.
- Minimal entrypoint (`services/agent-api/src/main.py`) or `uvicorn` config hooking FastAPI’s lifespan/startup if not already present.

## Step-by-Step Instructions
1. **App bootstrap**: Build a FastAPI app with shared middleware (auth stub, request ID injection, error handling) consistent with `docs/interfaces/api_contracts.md`. Ensure `POST /v1/chat` accepts the JSON schema described there (thread_id, messages, attachments, stream flag).
2. **Emitter lifecycle**: For streaming requests, create an `SSEEmitter` per invocation, spawn the LangGraph coroutine (or adapter stub) that accepts both the parsed payload and the emitter, and stream the emitter’s async iterator back to the client using the SSE content type (`text/event-stream`). Guarantee idle keep-alives (`: keep-alive` every ≤10s) so proxies don’t drop the connection.
3. **Cache short-circuit**: When the router/cache stack returns a final answer synchronously (cache hit), ensure the HTTP path still emits the canonical `cache_hit`/`done` frames so clients see a consistent stream.
4. **Error / interrupt handling**: Map LangGraph interruptions (HumanGate pauses, guardrail violations) to SSE frames defined in the contract. Bubble unexpected exceptions as `task_error` frames followed by HTTP 500 once the stream closes.
5. **Non-streaming fallback**: Honor `stream=false` by buffering the stream, collecting the last `done` payload, and returning the blocking JSON response described in the docs.
6. **Testing**: Unit-test the router + SSE adapter with an in-memory LangGraph stub that emits a deterministic list of events. Validate that headers (`Content-Type`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`) are set and that keep-alives continue until `done`.
7. **Docs**: Update `docs/interfaces/api_contracts.md` if request/response examples changed (e.g., header names, SSE ordering) and record the FastAPI module path for future agents.

## Definition of Done
- FastAPI app + `/v1/chat` streaming route implemented with proper SSE semantics, including keep-alives and graceful shutdown on completion/errors.
- Tests prove SSE formatting, cache-hit short-circuit behavior, and blocking fallback.
- Documentation references the new module + clarifies how to enable streaming in deployments.
- Standard verification commands (`uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`) captured in the final summary.

## Handoff Notes
- Capture how the LangGraph runner should be invoked (function signature, DI expectations) so the upcoming telemetry/Valkey tasks can reuse the same hook.
- Note any assumptions about auth middleware or request context so follow-on tasks can wire real auth/tenant resolution without breaking the SSE plumbing.
