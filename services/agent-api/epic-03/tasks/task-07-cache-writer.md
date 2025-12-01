# Task 07 — CacheWriter & Response Serialization

## System Snapshot
- Router + guardrails now determine the next subgraph and expose cache metadata (Task 06).
- Cache key helper + Valkey client stub exist (Task 05) but no writer logic.
- HumanGate and SSE telemetry will be addressed later (Tasks 08 & 12–13).

## What You Inherit
- Structured answers will be produced by modality subgraphs (Tasks 09–11). You will design serialization + caching contracts they can call.

## Goal
Implement the CacheWriter component that serializes positive answers (with citations + chunk IDs) into Valkey and exposes telemetry hooks for future tasks.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.3 (CacheWriter requirements).
2. `docs/overview/system_architecture.md` §3.3 (Valkey integration, pooling expectations).
3. `docs/data/schema_and_persistence.md` §§3.7–3.8 (telemetry tables recording cache hits/misses).
4. `docs/agents/implementation.md` §4.2 (cache short-circuit path).

## Implementation Scope & Files
- `services/agent-api/src/cache/CacheWriter.ts`
- Serialization helpers `services/agent-api/src/cache/responseSerializer.ts`
- Tests: `services/agent-api/tests/cache/CacheWriter.test.ts`
- Documentation update describing cache payloads + SSE placeholders.

## Step-by-Step Instructions
1. **Response Schema**:
   - Define interface for cached answers: `answer_text`, `citations[]`, `chunk_ids[]`, `workflow_plan_excerpt`, `model_metadata`.
   - Include versioning to invalidate older schema (add `schema_version`).
2. **CacheWriter Class**:
   - Accept `valkeyClient`, `cacheKey`, `payload`, `ttl`.
   - Serialize payload deterministically (sorted citations, etc.).
   - Record hit/miss placeholder events (call stub telemetry hooks; actual wiring in Task 13).
3. **Short-Circuit Helper**:
   - Provide `maybeServeFromCache(cacheKey)` to be used by Router/subgraphs to short-circuit future work when cache hits.
   - Ensure compatibility with LangGraph state (update `AgentState.cache_metadata`).
4. **Testing**:
   - Serialization determinism.
   - Cache write + read (Valkey client can be mocked in-memory).
   - Handling of TTL + error resilience (log + continue without crashing).
5. **Docs**:
   - Document cache payload schema and how to version it.
   - Mention SSE + telemetry events that will be implemented later.

## Definition of Done
- CacheWriter API available with tests.
- Response serializer documented + stable.
- Maybe-serve helper ready for downstream nodes.

## Handoff Notes
- Provide example usage for modality subgraphs.
- Note telemetry hooks to be filled in Task 13.
