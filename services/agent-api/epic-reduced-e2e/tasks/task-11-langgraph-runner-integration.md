# Task 11 — LangGraph Runner & Full Ingestion Integration

## System Snapshot
- Task 10 exposes configuration flags but the service still uses `UnconfiguredChatRunner`, so `/v1/chat` cannot reach real OpenAI/Voyage services.
- Document uploads terminate at the reduced-scope auto-complete path; Voyage never runs, no chunks/vectors are produced, and the pgvector-backed retrieval pipeline stays empty.
- Telemetry/rate-limiter hooks exist, but they have never been exercised under real model and ingestion load in the reduced stack.

## What You Inherit
- Full LangGraph graph implementation under `src/state`, `src/subgraphs`, and `src/nodes`.
- Shared data layer repositories + telemetry helpers.
- New env plumbing from Task 10 (flag + secret validation) but no actual runner wiring.

## Goal
Wire the Agent API to the real LangGraph runner **and** reuse the production ingestion pipeline so uploads/chat behave exactly like the live stack (aside from optional LocalStack for AWS). Outcomes:
1. Uploads trigger the same chunking + Voyage embedding flow used by `ArchaaS/lambdas/embedding_writer`, persisting vectors/metadata so pgvector queries work.
2. `/v1/chat` runs the full LangGraph graph (retrieval, reranking, policy nodes) against those vectors using OpenAI/Voyage.
3. Both code paths honor the Task 10 flag (text-only vs real tools) and stream telemetry/rate-limit data accordingly.

## Must Read / Inspect
1. `src/agent_api/http/streaming.py` for runner protocol and SSE expectations.
2. `state/agent_state.py`, `subgraphs/*`, `guardrails/*` to understand LangGraph wiring.
3. Existing OpenAI/Voyage client utilities under `packages/` or `services/` (search repo before coding new ones).

## Implementation Scope & Deliverables
- Introduce a `LangGraphChatRunner` (e.g., `src/services/langgraph_runner.py`) implementing `ChatRunnerProtocol`. Responsibilities:
  - Build `ChatRequestContext` into LangGraph state, execute the graph, and emit events via `SSEEmitter`.
  - Instantiate model/embedding/reranker clients using env-driven configs.
  - Surface structured errors (429, 5xx) with retry/backoff + metrics.
- Replace the reduced-scope ingestion shortcuts when real tools are enabled:
  - Reuse the existing ingestion workflow (e.g., call into the same modules leveraged by `ArchaaS/lambdas/embedding_writer` or extract shared helpers) to chunk Markdown, call Voyage to embed, and persist rows into `chunks`/`chunk_metrics`/pgvector.
  - Introduce a background worker or inline execution path that runs synchronously for smoke tests but shares the same code paths as production.
  - Update `DocumentUploadService` (and any CLI helpers) to branch: text-only path when reduced mode is active, full ingestion path when `use_real_tools` is set.
- Update `ReducedScopeWorkerRuntime`/pillar generation to rely on the new chunk data rather than heuristics.
- Update app startup to construct the runner + ingestion clients when real mode is active and register via `set_chat_runner`; delete the legacy `UnconfiguredChatRunner` wiring for runtime code paths (it should exist only as a unit-test helper).
- Add diagnostics logging which mode is active, which models are in use, and whether ingestion completed successfully.

## Step-by-Step Instructions
1. Catalogue existing LangGraph utilities and the ArchaaS ingestion code; extract shared helpers as needed so both services use the same ingestion steps.
2. Implement reusable clients/wrappers for OpenAI + Voyage with retry/backoff + metrics.
3. Build the runner class, unit-test with mocked clients, and ensure it supports blocking + streaming flows.
4. Replace the reduced ingestion auto-complete path when `use_real_tools` is enabled: load fixtures, invoke the shared chunker + embedding writer, persist vectors, update ingestion jobs, and refresh caches.
5. Connect the runner + ingestion pipeline inside `create_app()` (or dedicated bootstrap) based on Task 10 flags; emit clear logs when falling back to text-only mode.
6. Update pillar/artifact generation to rely on the real chunk/vector data.
7. Add tests covering:
   - Runner instantiation and error handling.
   - Upload-to-chat flow hitting mocked Voyage/OpenAI endpoints end-to-end.
   - Fallback to text-only path when the flag is disabled.
8. Run QA suite.

## Definition of Done
- `/v1/chat` uses the real LangGraph runner whenever real-tool mode is enabled, streaming responses derived from OpenAI output and Voyage retrieval data.
- Document uploads trigger the production-grade ingestion pipeline (chunking + Voyage + pgvector) so retrieval operates on real vectors.
- Pillar/artifact flows consume those vectors instead of heuristics.
- Tests cover runner + ingestion wiring; QA suite passes.

## Handoff Notes
- Document throughput limits and retry strategy; note any outstanding TODOs (e.g., multi-turn conversations, conversation cache warmup).
- If model selection remains hardcoded, list follow-ups for exposing env-based overrides.
- Capture any remaining ingestion gaps (e.g., S3 assets, async workers) for future epics.
