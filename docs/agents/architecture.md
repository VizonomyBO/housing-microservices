# ReAct Agent Architecture
Version: 2.0 (revamped stack)

## Purpose
Document the simplified ReAct agent that powers `agent-api`: a tool-driven loop with hybrid retrieval, advanced RAG techniques, and a Pyodide sandbox tool. Graph planners, cache layers, and Step Functions-era artifacts are deprecated and retained only as nullable schema remnants.

## Core design
- **Framework**: LangChain `create_agent` running on LangGraph with checkpointing for resilience and SSE streaming.
- **Retrieval stack**: BM25 + pgvector (Voyage `voyage-context-3`, 1024-d default) fused then reranked with Voyage `rerank-2.5`. HyDE/HyPE-style rewrites, contextual headers, and fusion diversity are encouraged before prompting.
- **Tools (current)**
  - `retrieve`: hybrid retrieval over `chunks` with filters; emits citations and scores.
  - `rerank/filter`: rerank utility and rerank-based filters to enforce score floors and diversity.
  - `document_status` / `list_documents`: attachment/status helpers to keep chat grounded on active docs.
  - `attachments_bulk`: bulk attach/detach with ownership enforcement (`thread_id` is UUID).
  - `pyodide_code`: Pyodide sandbox for light calculations/tabular work. Constraints: WebAssembly runtime, no filesystem, no arbitrary networking beyond `httpx`/`micropip` installs; keep payloads small and deterministic.
- **Response contract**: per-fact `[c#]` citations, `requires_sql`/`table_results` only when a tool produces them, and fail-fast errors when dependencies are missing (no cache fallbacks).

## Execution flow
1. **Request intake**: validate JWT, thread ownership, and document attachments. Block chat until attachments are `active`.
2. **Retrieval**: run BM25 + pgvector in parallel → fusion → rerank-2.5. Apply HyDE/HyPE expansions if recall is low; cap context to fit prompt budget.
3. **Tool loop**: ReAct chooses between retrieval-only answers, rerank/repair passes, Pyodide calculations, and attachment helpers. Loop limits are conservative (no unbounded recursion).
4. **Synthesis**: structure answers with contextual headers and strict citations. Reject/regenerate if facts lack `[c#]` markers or if rerank score floors are not met.
5. **Persistence**: store messages, tool calls, citations, and checkpoints via shared data layer repositories.

## Defaults & models
- Embeddings: Voyage `voyage-context-3` (length-normalized; cosine/dot equivalent). `VOYAGE_EMBEDDING_DIMENSIONS` default 1024; 256/512/2048 supported when the DB column matches.
- Reranker: Voyage `rerank-2.5` (required).
- Chat model: OpenAI (see env); no text-only fallback. Advanced RAG techniques (HyDE/HyPE, fusion, contextual headers) are required for quality, not optional.

## Deprecations
- Graph RAG/planner subgraphs, Step Functions/Lambda ingestion hooks, Valkey cache/rate limiter, reduced-scope/demo modes, and telemetry extras are deprecated. Keep related schema fields nullable and documented only.
- Swagger aggregator remains disabled.
