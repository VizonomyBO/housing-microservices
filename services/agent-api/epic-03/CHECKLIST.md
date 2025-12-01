# Epic 3 Agent API Task Checklist

Complete tasks sequentially. Each agent should mark the checkbox upon finishing and leave notes/links in their PR/summary.

1. - [x] [Task 01 — AgentState Schema Foundation](tasks/task-01-agent-state-schema.md) — Added `src/state/agent_state.py` + tests/state coverage for serialization helpers.
2. - [x] [Task 02 — Checkpoint Persistence & HITL Metadata](tasks/task-02-checkpoint-persistence.md) — Added checkpoint repository/service + HITL tests.
3. - [x] [Task 03 — InputNormalizer & AttachmentScopeLoader Nodes](tasks/task-03-input-normalizer.md) — Implemented LangGraph nodes + tests, updated docs + scope hash plumbing.
4. - [x] [Task 04 — GraphRetriever & GraphSummarizer Nodes](tasks/task-04-graph-retriever-summarizer.md) — Added graph data utilities + LangGraph nodes, TTL/telemetry plumbing, tests, and doc updates.
5. - [x] [Task 05 — WorkflowPlanner Node & Cache Key Schema](tasks/task-05-workflow-planner-cache.md) — WorkflowPlanner node, cache helper/stub, docs/tests added (2025-12-01).
6. - [x] [Task 06 — Router Classification & Guardrail Policies](tasks/task-06-router-guardrails.md) — Added `src/guardrails/*`, router node/tests, and docs for policy codes + routing sample (2025-12-01).
7. - [ ] [Task 07 — CacheWriter & Response Serialization](tasks/task-07-cache-writer.md)
8. - [ ] [Task 08 — HumanGate Pause/Resume Node](tasks/task-08-human-gate.md)
9. - [ ] [Task 09 — Informational & Analyst Subgraphs](tasks/task-09-informational-analyst.md)
10. - [ ] [Task 10 — Numerical Subgraph (Text-to-SQL + Validators)](tasks/task-10-numerical.md)
11. - [ ] [Task 11 — Vision Subgraph & Multimodal Responses](tasks/task-11-vision.md)
12. - [ ] [Task 12 — SSE Streaming Contract & Event Emitters](tasks/task-12-sse-contract.md)
13. - [ ] [Task 13 — Metrics, Cache Observability & Shared Data Layer Writers](tasks/task-13-telemetry-cache-observability.md)
