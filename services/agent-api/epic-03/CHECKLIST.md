# Epic 3 Agent API Task Checklist

Complete tasks sequentially. Each agent should mark the checkbox upon finishing and leave notes/links in their PR/summary.

1. - [x] [Task 01 — AgentState Schema Foundation](tasks/task-01-agent-state-schema.md) — Added `src/state/agent_state.py` + tests/state coverage for serialization helpers.
2. - [x] [Task 02 — Checkpoint Persistence & HITL Metadata](tasks/task-02-checkpoint-persistence.md) — Added checkpoint repository/service + HITL tests.
3. - [x] [Task 03 — InputNormalizer & AttachmentScopeLoader Nodes](tasks/task-03-input-normalizer.md) — Implemented LangGraph nodes + tests, updated docs + scope hash plumbing.
4. - [x] [Task 04 — GraphRetriever & GraphSummarizer Nodes](tasks/task-04-graph-retriever-summarizer.md) — Added graph data utilities + LangGraph nodes, TTL/telemetry plumbing, tests, and doc updates.
5. - [x] [Task 05 — WorkflowPlanner Node & Cache Key Schema](tasks/task-05-workflow-planner-cache.md) — WorkflowPlanner node, cache helper/stub, docs/tests added (2025-12-01).
6. - [x] [Task 06 — Router Classification & Guardrail Policies](tasks/task-06-router-guardrails.md) — Added `src/guardrails/*`, router node/tests, and docs for policy codes + routing sample (2025-12-01).
7. - [x] [Task 07 — CacheWriter & Response Serialization](tasks/task-07-cache-writer.md) — CacheWriter + response serializer + docs/tests (2025-12-02)
8. - [x] [Task 08 — HumanGate Pause/Resume Node](tasks/task-08-human-gate.md) — Added HumanGate service/node, transcript metadata, docs, and tests (2025-12-02)
9. - [x] [Task 09 — Informational & Analyst Subgraphs](tasks/task-09-informational-analyst.md) — Implemented Informational/Analyst nodes, AgentState contracts, tests, and acceptance doc updates (2025-12-02).
10. - [x] [Task 10 — Numerical Subgraph (Text-to-SQL + Validators)](tasks/task-10-numerical.md) — Added numerical state contracts, TextToSQL/Polars/validator nodes, artifacts, tests, and acceptance notes (2025-12-02).
11. - [x] [Task 11 — Vision Subgraph & Multimodal Responses](tasks/task-11-vision.md) — Added vision router/reasoner/responder nodes, guardrail codes, docs, and tests (`tests/subgraphs/vision/test_vision_nodes.py`) (2025-12-02).
12. - [x] [Task 12 — SSE Streaming Contract & Event Emitters](tasks/task-12-sse-contract.md) — Added streaming event models/emitter/decorator, instrumented LangGraph nodes + cache/HITL hooks, docs/tests updated (2025-12-02).
13. - [x] [Task 13 — Metrics, Cache Observability & Shared Data Layer Writers](tasks/task-13-telemetry-cache-observability.md) — Added telemetry modules, wired SSE metric refs, CacheObservability writers, docs, and telemetry tests (`tests/telemetry/*`) (2025-12-02).
14. - [x] [Task 14 — Streaming Gateway & SSE Proxy](tasks/task-14-sse-gateway.md) — Build the FastAPI `/v1/chat` streaming endpoint, wire `SSEEmitter`, and proxy LangGraph events to clients with keep-alives. (2025-12-02)
15. - [x] [Task 15 — Metrics Endpoint & Telemetry Bootstrap](tasks/task-15-prometheus-metrics.md) — Added settings/env helpers, FastAPI lifespan wiring, secured `/metrics`, DI hooks for metrics/cache observability/DB sessions, streaming runner plumbing, tests (`tests/http/test_metrics_route.py`), and doc updates (2025-12-02).
16. - [ ] [Task 16 — Production Valkey Client & Cache Wiring](tasks/task-16-valkey-integration.md) — Replace the in-memory stub with a real Valkey client, configuration, and integration tests/documentation.
