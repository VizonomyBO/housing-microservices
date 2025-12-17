# LLM Eval Quality Improvements (ReAct + Retrieval)

Tighten eval quality for the ingestion-first, text-only stack. The agent is a ReAct loop with hybrid retrieval (BM25 + pgvector) using Voyage `voyage-context-3` embeddings and `rerank-2.5`, plus Pyodide for light calculations. Graph/planner/reduced-scope and cache/rate-limiter fallbacks are deprecated.

## Scope & prerequisites
- Run against the live stack (`.env.prod`) with real OpenAI/Voyage keys. No stubs or mock judges.
- Use the FastAPI ingestion service to load eval documents (MarkItDown → contextual chunking → voyage-context-3 embeddings → pgvector). Reuse smoke uploads when possible to avoid dedupe.
- Judges: `gpt-5.1` with `EVAL_REASONING_EFFORT=medium` (bump to `high` for heavy numeric cases).

## Retrieval upgrades
- **HyDE/HyPE rewrites** when recall is weak; fuse BM25 + vector candidates before reranking.
- **Voyage defaults**: `voyage-context-3` embeddings (1024-d default; 256/512/2048 allowed when DB matches) and `rerank-2.5` required.
- **Contextual headers**: keep section/page titles in the prompt; prefer proposition-aware chunks over flat blocks.
- **Fusion diversity**: enforce diversity to avoid single-doc domination; apply rerank score floors before prompting.
- **Numeric-aware rerank**: boost candidates with numeric evidence when queries demand numbers; never bypass rerank.

## Prompt & agent shaping
- Tool-first prompts: retrieve → rerank/repair → (optional) Pyodide for deterministic calculations/tabular work (Wasm, no filesystem; `httpx`/`micropip` installs only).
- Structured outputs for numeric/table questions; otherwise concise prose with per-fact `[c#]` citations.
- Require citation coverage before finalizing; regenerate once when coverage is missing, otherwise return a grounded failure.

## Eval harness guidance
- Hit real endpoints; do not bypass tools/retrieval inside the eval runner.
- Capture retrieval traces and citations in artifacts; fail fast on missing dependencies (OpenAI/Voyage/ingestion).
- Prefer scenarios that exercise ingestion activation, attachment gating, rerank/repair loops, and Pyodide calculations.

## Acceptance criteria
- Retrieval uses voyage-context-3 + rerank-2.5 with HyDE/HyPE and contextual headers.
- Prompts enforce per-fact citations and structured numeric outputs where applicable.
- Eval thresholds reflect groundedness/faithfulness improvements; no fallbacks to caches or stubbed flows.
