# ReAct Agent Implementation

This document explains how the simplified agent runs inside `agent-api` after the architecture revamp.

## Request lifecycle
1. **Auth & ownership**: validate JWT via auth-service/user-service. Enforce UUID `thread_id` ownership; reject chat if attachments are missing or documents are not `active`.
2. **State hydrate**: load conversation history and prior checkpoints (LangGraph MemorySaver). No cache layer; every hop relies on real persistence and retrieval.
3. **Retrieval**:
   - Run BM25 and pgvector (Voyage `voyage-context-3`) in parallel, filter by doc IDs/country/tags.
   - Fuse results, then rerank with Voyage `rerank-2.5`.
   - If recall is weak, trigger HyDE/HyPE rewrites and rerun retrieval; apply contextual headers to keep section titles in the prompt.
4. **Tool loop (ReAct)**:
   - Choose between retrieval-only answers, rerank/repair passes, document status/listing, attachment bulk ops, and Pyodide code execution for light calculations.
   - Pyodide guardrails: WebAssembly sandbox, no filesystem, no arbitrary networking; install minimal extras with `micropip` + `httpx`.
   - Loop limits prevent runaway retries; all failures surface as explicit errors (no fallback stubs).
5. **Synthesis**:
   - Build answers with contextual headers and per-fact `[c#]` citations.
   - Validate that every claim is cited; regenerate once if coverage is missing, otherwise return a grounded failure.
6. **Persistence**: store messages, tool calls, citations, and checkpoints via shared data layer repositories in `housing`.

## Retrieval defaults
- Embeddings: Voyage `voyage-context-3` (default 1024-d; 256/512/2048 supported when DB matches).
- Reranker: Voyage `rerank-2.5` is mandatory.
- Advanced RAG: HyDE/HyPE expansions, fusion of BM25 + vector, rerank score floors, diversity caps, and contextual headers are required to maintain quality.

## Error handling & safety
- Fail fast when OpenAI/Voyage/ingestion dependencies are missing; no cache/rate-limiter fallbacks.
- Attachment gating blocks chat on non-active documents; ingestion failures must be fixed upstream.
- Graph RAG/planner, Step Functions/Lambda hooks, Valkey cache, and reduced-scope modes are deprecated and should not be reintroduced.
