# Task 04 — GraphRetriever & GraphSummarizer Nodes

## System Snapshot
- Input normalization and attachment loading nodes exist (`services/agent-api/src/nodes/retrieval/InputNormalizerNode.ts`, `AttachmentScopeLoaderNode.ts`).
- State + checkpoint repositories are available from Tasks 01–02.
- No graph-context nodes exist yet; you will connect to graph tables.

## What You Inherit
- Normalized payloads containing document/workflow context.
- Shared data layer clients supporting graph queries referencing `graph_edge_evidence_rollup` and `graph_hot_entities`.

## Goal
Build nodes that pull contextual knowledge graph data and transform it into prompt-ready structures.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.2 (graph retrieval requirements).
2. `docs/data/schema_and_persistence.md` §3.4 (graph schema + rollups).
3. `docs/agents/implementation.md` §3.2 (graph context planning in LangGraph).
4. `docs/overview/system_architecture.md` §3.3 (cache + graph refresh strategy).

## Implementation Scope & Files
- `services/agent-api/src/nodes/retrieval/GraphRetrieverNode.ts`
- `services/agent-api/src/nodes/retrieval/GraphSummarizerNode.ts`
- Supporting query utilities under `services/agent-api/src/nodes/retrieval/graph/`
- Tests under `services/agent-api/tests/nodes/retrieval/graph/`
- Docs update describing refresh logic + prompt format.

## Step-by-Step Instructions
1. **GraphRetriever**:
   - Query `graph_edge_evidence_rollup` and `graph_hot_entities` filtered by conversation intent, tenant, and attachments.
   - Support `refresh: boolean` input; if caches stale, re-query underlying tables.
   - Return structured graph context (entities, relations, evidence, timestamps).
2. **Refresh Policy**:
   - Implement TTL-based freshness (read TTL from config). Document behavior.
   - Provide telemetry hook (stub) for cache hits/misses (Task 13 will wire actual metrics).
3. **GraphSummarizer**:
   - Convert graph context into textual + structured prompt pieces with deterministic ordering and token budgeting.
   - Provide fallback summaries if graph empty.
4. **Testing**:
   - Graph retrieval filtering by tenant and attachments.
   - Refresh policy: forced refresh should bypass cached data (simulate by toggling flag).
   - Summaries maintain deterministic ordering and token-length constraints.
5. **Docs**:
   - Update LangGraph diagram to show GraphRetriever → GraphSummarizer sequence.
   - Document TTL/refresh settings referencing config file.

## Definition of Done
- Graph nodes exported and wired for dependency injection.
- Tests cover retrieval, refresh, and summarization logic.
- Documentation describes inputs/outputs and refresh policy.

## Handoff Notes
- Provide example graph summary output for WorkflowPlanner (next task).
- Note any TODOs around telemetry hooks for Task 13.
