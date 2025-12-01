# Task 12 — SSE Streaming Contract & Event Emitters

## System Snapshot
- Core nodes/subgraphs (Tasks 01–11) exist with TODO hooks for streaming + telemetry.
- No SSE implementation yet; API contract defined in `docs/interfaces/api_contracts.md` §3.

## What You Inherit
- Each node exposes events that need to be streamed (`task_start/end`, cache events, HumanGate pauses, etc.).
- HTTP server stack (see `services/agent-api` once created) should already support streaming responses (if not, document gaps).

## Goal
Implement the SSE helper library and ensure every LangGraph transition emits events that comply with the documented contract.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.5 (SSE + metrics requirements).
2. `docs/interfaces/api_contracts.md` §3 (detailed SSE envelope + event types).
3. `docs/overview/system_architecture.md` §3.7 (observability + streaming considerations).
4. Review Tasks 01–11 outputs to know where to insert emitters (look for TODO comments).

## Implementation Scope & Files
- `services/agent-api/src/streaming/sse_emitter.py`
- `services/agent-api/src/streaming/events.py` (event type definitions)
- Middleware or decorator `services/agent-api/src/streaming/with_sse.py` for LangGraph nodes/controllers.
- Tests `services/agent-api/tests/streaming/test_sse_emitter.py`
- Documentation updates (SSE appendix in `docs/agents/implementation.md`).

## Step-by-Step Instructions
1. **Envelope Definition**:
   - Implement canonical structure: `{ event, timestamp, conversation_id, task_id, payload }`.
   - Support event types: `task_start`, `task_end`, `cache_hit`, `cache_miss`, `cache_write`, `hitl_pause`, `hitl_resume`, `telemetry_snapshot`.
2. **Emitter Helper**:
   - Provide async iterator that nodes can push events into; ensures proper SSE formatting (`data: ...\n\n`).
   - Handle connection keep-alive and back-pressure.
3. **Integration Points**:
   - Update nodes/subgraphs to import emitter helper and fire events at key transitions (ensure minimal duplication via decorator).
   - Document exactly where each event is emitted (Router decisions, CacheWriter hits, HumanGate pause/resume, subgraph start/end).
4. **Testing**:
   - Unit test emitter: event formatting, heartbeat/keepalive, error handling.
   - Integration test stub LangGraph flow to ensure ordered events.
5. **Docs**:
   - Provide event table (name, trigger, payload fields) referencing contract doc.
   - Include example SSE stream transcript for QA.

## Definition of Done
- SSE emitter + decorators implemented with tests.
- All nodes reference emitter hooks (even if actual telemetry payload minimal for now).
- Documentation describes how clients consume the stream and map events to UI.

## Handoff Notes
- Note any outstanding performance tuning for Task 13 (metrics integration).
- Provide CLI command to run streaming tests.
