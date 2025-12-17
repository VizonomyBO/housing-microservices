# Retrieval & Agent Configuration

## Objectives
Keep retrieval deterministic and high quality for the text-only stack: hybrid BM25 + pgvector with Voyage `voyage-context-3` embeddings and `rerank-2.5`, plus advanced RAG techniques (HyDE/HyPE, contextual headers, fusion diversity). Graph RAG, caches, and rate-limit plumbing are deprecated.

## Defaults
- **Embeddings**: Voyage `voyage-context-3`, default `VOYAGE_EMBEDDING_DIMENSIONS=1024` (supports 256/512/2048 when DB matches). Embeddings are length-normalized (cosine/dot equivalent).
- **Reranker**: Voyage `rerank-2.5` (required).
- **Retrievers**: BM25/FTS and pgvector in parallel; fuse then rerank.
- **Context budget**: keep prompts within token budget; prefer diversity across documents instead of single-doc domination.

## Recommended pipeline
1. Normalize prompt, enforce country/doc filters, and hydrate conversation scope.
2. Run BM25 + pgvector in parallel; cap candidates per channel to avoid context blowup.
3. Fuse (RRF/MMR-style), then rerank with `rerank-2.5`.
4. If recall is weak:
   - Generate HyDE/HyPE variants and rerun retrieval.
   - Apply contextual headers to carry section titles into the prompt.
   - Require rerank score floors before proceeding.
5. Build prompt with per-fact `[c#]` placeholders and insist on full citation coverage.
6. Regenerate once if coverage or rerank thresholds fail; otherwise return a grounded failure (no silent fallbacks).

## Filters & fields
- Filter by `document_id`, `country_code`, `tags`, and `status=active`.
- Use chunk metadata (section titles, page numbers) as contextual headers to improve grounding.
- Table/image retrieval is deprecated; keep chunk types text-only for now.

## Tooling hooks
- Retrieval tool emits scores and chunk IDs; rerank tool can drop low-score items and enforce diversity.
- Attachment/status tools ensure only `active` documents are used; fail fast otherwise.
- Pyodide code tool is for light computation only (Wasm, no filesystem; networking limited to `httpx` + `micropip` installs).

## Deprecations & constraints
- No Valkey cache or rate-limiter integration in the agent loop.
- Graph RAG/workflow planners are deprecated; related tables remain nullable and documented only.
- Reduced-scope/demo toggles are removed; always use the ingestion-first, real-retrieval path.
