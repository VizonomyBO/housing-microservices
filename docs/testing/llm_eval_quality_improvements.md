# LLM Eval Quality Improvements (RAG + Prompting Hardening)

Raise answer correctness/faithfulness for the reduced E2E scenarios by tightening retrieval, prompt structure, and response validation. Success = higher thresholds in the eval suite with `uv run pytest tests/evals -m eval` passing on real endpoints.

## Scope & prerequisites
- Run against the live stack using `.env.prod`, `EVAL_USER_ID`, and real OpenAI credentials. Default judge: `gpt-5.1` with `EVAL_REASONING_EFFORT=medium` (bump to `high` for numeric prompts).
- Work inside `services/agent-api` and keep artifacts under `tests/evals/artifacts/` (gitignored).
- Keep uploads unique when re-running reduced E2E flows to avoid dedupe short-circuits; reuse existing doc IDs in eval datasets.

## Retrieval upgrades
- **HyDE rewrite (Hypothetical Document Embeddings)** — Generate a short hypothetical answer from the user question, embed it, and search with both the original query and the hypothetical (per [HyDE, arXiv 2212.10496](https://arxiv.org/abs/2212.10496)). Keep top-k from each, then dedupe by doc/chunk ID.
- **Numeric-aware reranker** — When the query expects numbers/percentages:
  - Detect required entities/metrics (district names, percentages, dollar amounts, KPI values).
  - Score chunks with a numeric bonus (e.g., `score = sim + 0.1 * has_numeric + 0.05 * entity_overlap`) so number-bearing chunks outrank prose. Use a cross-encoder or lightweight LLM reranker; reference [Pinecone two-stage retrieval](https://www.pinecone.io/learn/series/rag/rerankers/) for the pattern.
  - If no numeric chunks survive, re-retrieve with a smaller chunk window or expanded filters instead of proceeding with empty facts.
- **Model upgrades (no shortcuts)** — Default embeddings use `voyage-3-large` and hybrid candidates are reranked with Voyage `rerank-2.5` before prompt assembly. When the embedding model changes, re-embed existing chunks in-place (no re-upload) via `uv run python -m agent_api.cli reembed-chunks --batch-size 64 [--document-id ...]`, then refresh views.
- **Diversified fusion (coverage-aware RRF/MMR)** — Blend hybrid candidates with reciprocal-rank fusion and per-document caps; add funding/reporting cue boosts so policy + ledger/reporting evidence surface together without doc-name hardcoding. Prefer diversity over single-doc dominance; keep a mix of policy, funding, and reporting spans when available.
- **Table extraction for ledger/KPI docs** — After reranking, run a table-aware pass on kept chunks (MarkItDown/`pandas.read_fwf`/`read_csv` on TSV) to extract rows keyed by entity/date. Feed extracted cells (entity, metric, value, unit, line number) into the prompt context.
- **Context constraints**
  - Restrict retrieval to provided doc IDs and cap chunk tokens to fit the prompt; trim to the smallest set that covers required entities/metrics.
  - Re-run retrieval if checklist items (below) are missing from kept contexts.

## Prompt & agent shaping
- **Pre-answer checklist** — Before drafting, list required items from the question (entities, metrics, units, date ranges). Attach retrieval spans that satisfy each item.
- **Structured schema** — Ask the model to emit JSON (or bullet-equivalent) shaped as:
  ```json
  {
    "facts": [
      {"item": "District 9 housing units", "value": 125, "unit": "units", "citation": "[1]"},
      {"item": "KPI score", "value": 0.84, "unit": "score", "citation": "[2]"}
    ],
    "answer": "District 9 has 125 units ...",
    "citations": ["[1] ledger.md#L42", "[2] kpi.md#L18"]
  }
  ```
  Require every fact to carry a citation marker; reject/regenerate if any field is missing or `null`. See JSON-schema style enforcement guidance ([structured output overview](https://medium.com/@deolesopan/structured-outputs-json-schemas-make-your-llms-speak-api-4f22eb5bf3ac)).
- **Citation/grounding rules**
  - “Use only values present in retrieved text; do not round beyond the source; omit anything uncited.”
  - Map citation markers to chunk IDs/line anchors in the prompt to prevent drift.
- **Reasoning effort** — Set `reasoning.effort` to `medium`/`high` for numeric prompts; keep `low` only for simple textual Q&A to save tokens.

## Self-check & regeneration
- Validate that every checklist item has a fact with a citation; if not, regenerate using the same contexts (do not widen to unrelated docs).
- Enforce numeric integrity: reject outputs with invented ranges/averages; require exact matches to extracted values.
- If citations are missing or counts differ from extracted tables, re-render the final answer; fall back to “not found in provided documents” rather than hallucinating.

## Validation & thresholds
- Raise reduced E2E thresholds toward the earlier gates (faithfulness/answer_relevance ≈ 0.5 per scenario) in `tests/evals/datasets/reduced_e2e_smoke.yaml`; keep scenario-specific notes inline.
- Keep deterministic checks (citation coverage, empty-context guard) enabled. If a metric regresses, adjust retrieval/prompting before lowering thresholds.
- **Never hardcode eval prompts/answers into the agent.** Retrieval/prompt shaping must stay generic; scenario specifics belong only in eval datasets/harness—production prompts cannot contain baked eval cases.
- **Use the real retrieval path.** Avoid “preview-only” or heuristic-only reranking; invoke the production retrieval stack (vector + BM25/FTS where available) so evals measure true retrieval quality. Do not perform retrieval inside the eval handler that bypasses APIs; send requests through the same endpoints used in production. If retrieval fails, surface the error instead of falling back to mocked/preview content.
- **Citation validation must be deep.** Cite actual retrieved chunks and validate that citation markers align to chunk IDs/text, not just presence of brackets; preserve `[id]` and `[SQL_ROWS]` markers for frontend rendering.
- **Planned hybrid retrieval upgrade:** add BM25/FTS alongside pgvector, retrieve top-N from both, then rerank (e.g., weighted sum or LLM reranker) before prompting. This replaces any heuristic-only preview selection.

## Runbook (pytest)
1) From repo root: `cd services/agent-api`
2) Export env:
   ```bash
   set -a && source ../.env.prod && set +a
   export EVAL_USER_ID=<uuid>
   export EVAL_REASONING_EFFORT=medium  # or high for numeric-heavy cases
   # optional overrides
   export EVAL_JUDGE_MODEL=gpt-5.1
   ```
3) Execute evals: `uv run pytest tests/evals -m eval`
4) Inspect artifacts: `ls tests/evals/artifacts/evals/*/*/result.json` (gitignored).

## Troubleshooting
- **No numeric spans retrieved**: lower chunk size, increase top-k, or rerun HyDE rewrite; prefer re-retrieval over extrapolating.
- **Citations fail validation**: ensure chunk IDs/line anchors are passed into the prompt; keep per-fact markers, not a single list.
- **Judge/token churn**: if `gpt-5.1` costs spike, temporarily run with fewer scenarios but do not relax structured output or citations.

## Acceptance criteria
- Retrieval includes HyDE rewrite + numeric-aware rerank + table extraction for ledger/KPI contexts.
- Agent prompt enforces structured output with explicit numbers and per-fact citations; self-check/regeneration guards are in place.
- Stricter thresholds restored in `tests/evals/datasets/reduced_e2e_smoke.yaml`, and `uv run pytest tests/evals -m eval` passes against the live stack.
- This document reflects the updated steps and commands, with sources recorded above.
