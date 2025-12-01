# Task 05 — WorkflowPlanner Node & Cache Key Schema

## System Snapshot
- Graph context nodes (Task 04) now produce structured summaries.
- Valkey cache not yet integrated; you will introduce cache key helpers while implementing WorkflowPlanner.
- Workflow definitions live in `workflow_versions` and `workflow_version_diffs` per Epic 1.

## What You Inherit
- Normalized inputs, attachment scopes, and graph summaries.
- Shared data layer clients for workflow tables (`packages/shared_data_layer/workflows`).

## Goal
Create the `WorkflowPlanner` node that projects workflow graphs into user-facing plans, and define the cache key schema used across downstream nodes.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.2 (WorkflowPlanner expectations + cache keys).
2. `docs/data/schema_and_persistence.md` §3.5 (workflow tables, versioning, diffs).
3. `docs/overview/system_architecture.md` §3.3 (Valkey topology, cache layering).
4. `docs/agents/implementation.md` §3.3 (workflow planning subgraph).

## Implementation Scope & Files
- `services/agent-api/src/nodes/retrieval/WorkflowPlannerNode.ts`
- Cache helper module `services/agent-api/src/cache/cacheKeys.ts` + Valkey client wrapper stub `services/agent-api/src/cache/valkeyClient.ts` (no network ops beyond interface scaffolding yet).
- Tests under `services/agent-api/tests/nodes/retrieval/workflow/` and `tests/cache/`.
- Documentation snippet describing cache key schema.

## Step-by-Step Instructions
1. **Cache Key Helper**:
   - Implement `buildRetrievalCacheKey({ conversationId, intent, workflowVersion, documentHashes })`.
   - Include serialization + normalization (lowercase, sort hashes deterministically).
2. **WorkflowPlanner Node**:
   - Load workflow graph/diffs for the requested workflow version.
   - Produce ordered plan steps with metadata (version, diff summary, prerequisites).
   - Attach computed cache key + `cache_metadata` (hit/miss placeholder) to the node output.
3. **Valkey Client Stub**:
   - Define interface for `get`, `set`, `tagHit`, `tagMiss` but you may mock implementations (actual wiring handled later).
4. **Testing**:
   - Cache key helper tests (idempotent, handles varying hash orders).
   - WorkflowPlanner plan generation for workflows with diffs.
   - Ensure node output includes cache metadata stub.
5. **Docs**:
   - Document cache key format, TTL, and when GraphRetriever/WorkflowPlanner must invalidate caches.

## Definition of Done
- WorkflowPlanner node returns plan + cache metadata.
- Cache key helper available for reuse.
- Tests cover helper determinism and plan generation.
- Docs updated with cache schema narrative.

## Handoff Notes
- Provide sample cache key + plan snippet for Router/cache tasks.
- Call out TODOs for actual Valkey operations (handled later in Task 07 & Task 13).
