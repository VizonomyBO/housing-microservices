# LLM Eval Quality Improvements (RAG + Prompting Hardening)

This task describes how to raise answer correctness/faithfulness for the reduced E2E scenarios by tightening retrieval, prompt structure, and response validation. Success is measured by re-enabling higher thresholds in the eval suite and passing `uv run pytest tests/evals -m eval`.

## Objectives
- Improve grounding for numeric/textual facts (district counts, percentages, dollar amounts, KPI scores).
- Enforce structured answers with citations and explicit numbers.
- Reduce reliance on threshold loosening by upgrading retrieval + generation steps.

## Plan (implementation outline)
1) **Retrieval upgrades**
   - Add a HyDE-style rewrite: synthesize a hypothetical answer or enriched query that includes expected entities/metrics; use both original + rewritten query for retrieval.
   - Introduce a numeric-aware reranker: favor chunks containing numbers/percentages and target entities; down-rank chunks without numerics when the prompt expects them.
   - For table-like docs (ledger/KPI), run a lightweight table extractor on selected chunks and feed extracted cells into the context passed to the agent.
   - Tighten constraints: restrict to provided doc IDs, limit tokens per chunk, and re-retrieve if required entities/metrics from the rewritten query are missing in the kept contexts.

2) **Prompt/agent shaping**
   - Add a pre-answer checklist step: list required facts/figures from the question, then quote/cite exact spans from retrieved text.
   - Enforce a structured response schema (JSON or rigid bullets) with `facts[{item, number/value, citation}]`, `answer`, and `citations`. Reject/regenerate if any required field is missing.
   - Hard numeric constraint: “Include the exact figures from the docs; do not generalize; omit anything not in cited text.” Require each fact to carry a citation marker.
   - Increase agent `reasoning.effort` to `medium`/`high` for numeric scenarios.

3) **Self-checks and citation enforcement**
   - If any required number/entity is absent in the draft answer, auto-regenerate using the same contexts.
   - Refuse to emit final text without citations; ensure each fact is individually cited.

4) **Validation**
   - Re-raise eval thresholds toward prior values (faithfulness/answer_relevance ≈ 0.5 for the reduced E2E scenarios).
   - Run `cd services/agent-api && uv run pytest tests/evals -m eval` with `.env.prod`, `EVAL_REASONING_EFFORT` set as needed, and real OpenAI credentials.
   - Adjust prompts/retrieval heuristics iteratively until all scenarios pass at higher thresholds.

## Acceptance criteria
- Retrieval pipeline includes HyDE rewrite + numeric-aware rerank, and table extraction for KPI/ledger contexts.
- Agent prompt enforces structured output with explicit numbers and per-fact citations; self-check/regeneration in place.
- Thresholds in `tests/evals/datasets/reduced_e2e_smoke.yaml` are restored to stricter values and the eval suite passes.
- Documentation updates summarizing the changes and how to run the evals.***
