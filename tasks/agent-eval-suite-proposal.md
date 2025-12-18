# Agent Eval Suite Proposal (Research-Informed)

## Purpose
- Provide a research-backed design for an OOP-friendly, pytest-driven evaluation suite that exercises the Agent API end-to-end (HTTP chat/SSE, attachments, retrieval/rerank) using prod data and `gpt-5.1` as the judge.

## References (key takeaways)
- DeepEval: pytest-style LLM unit tests, 30+ research-backed metrics, and component-level tracing for agents; supports LLM-as-judge with retries and configurable models ([DeepEval quickstart](https://deepeval.com/docs/getting-started)).
- OpenAI evals: define `data_source_config` schemas plus `testing_criteria` graders; run evals over datasets and inspect results via dashboard/webhooks ([OpenAI evals guide](https://platform.openai.com/docs/guides/evals)).
- LangSmith: custom LLM-as-judge evaluators with feedback schemas, pre-built correctness/hallucination checks, and SDK/UI flows for offline/online evals ([LangSmith LLM-as-judge](https://docs.langchain.com/langsmith/llm-as-judge)).
- Promptfoo: `llm-rubric` model-graded assertions with rubric prompts, thresholds, and provider overrides for judge models ([Promptfoo llm-rubric](https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/llm-rubric/)).

## Design Goals
- End-to-end over HTTP with real deps (no stubs): chat/SSE, attachments, retrieval, rerank, footnoted citations.
- OOP composition: scenario objects + clients + judge runners; pytest markers for env gating.
- Reuse seeded docs (MEX/ARG) and shared credentials; fail fast on missing env/keys.
- Metrics align to voyage-context-3 + rerank-2.5 hybrid stack and attachment gating semantics.

## Proposed Stack
- **Harness:** pytest + rich fixtures; base HTTP client wrapping Agent API endpoints; optional async SSE client.
- **Judge/metrics:** primary: LLM-as-judge via `gpt-5.1` with high reasoning; secondary: deterministic checks (status codes, presence of citations, attachment gating). Allow plug-in metrics from DeepEval or Promptfoo when helpful:
  - DeepEval GEval/AnswerRelevancy for groundedness, regression-friendly scores.
  - Promptfoo `llm-rubric` for rubric-style scoring when we need external config or multilingual rubrics.
  - Custom judge prompts for citation alignment and retrieval recall.
- **Data:** prod DB, provided doc IDs for attachments.
- **Execution:** `uv run pytest -m "agent_eval"` with env vars loaded via `use_env.sh` (prod profile). Optional `--end-to-end` marker for heavier flows.

## Suggested Layout
- `tests/evals/`
  - `clients.py`: HTTP client (sync + optional SSE) wrapping auth, documents, conversations, attachments, chat; typed responses; token management.
  - `scenarios/base.py`: abstract Scenario with setup/teardown hooks, run() returning EvalResult.
  - `scenarios/retrieval.py`: checks grounding, rerank ordering, HyDE-style rewrite coverage.
  - `scenarios/citations.py`: ensures `[c#]` footnotes map to attached docs; validates citation spans.
  - `scenarios/attachments.py`: enforces attachment gating, visibility rules.
  - `judges/llm_judge.py`: shared LLM-as-judge helper (prompt templates for correctness, grounding, style, safety); configurable model params; retries with jitter.
  - `fixtures.py`: pytest fixtures for access token, conversation factory, document attachments, and seeded datasets.
  - `markers.py`: custom markers (`agent_eval`, `requires_prod`, `longrun`).

## Key Flows to Cover
- **Authentication:** register/login with provided eval user; token reuse between tests.
- **Document lifecycle:** ensure provided doc IDs are active; attach to conversations; verify visibility and ownership rules (shared/no user).
- **Chat blocking mode:** blocking responses with citations; SSE path sanity (if available) for streaming correctness.
- **Retrieval quality:** RAG hybrid expectations (BM25+vector+rerank) — test that top contexts include attached doc passages; rerank moves relevant passages upward.
- **Citation integrity:** every cited footnote references attached doc IDs; no orphan citations; numeric-aware answers remain grounded.
- **Attachment gating:** blocked until ingestion active; fail if unowned/hidden docs are used.
- **Safety/formatting:** judge for instruction adherence, refusal handling, and footnote structure.

## Judge & Metrics Strategy
- **LLM-as-judge prompt set (gpt-5.1, reasoning effort high):**
  - Correctness vs expected span (when deterministic).
  - Grounding: did answer stay within retrieved passages? (requires supplying retrieved snippets + docs).
  - Citation alignment: each `[c#]` justified by quoted span from same doc.
  - Helpfulness/conciseness: penalize verbosity; enforce structured footnotes.
  - Safety/compliance: detect leakage of PII/credentials and refusal quality.
- **Deterministic metrics:**
  - HTTP status + schema validation.
  - Presence/format of citations; uniqueness of `[c#]`.
  - Attachment enforcement (403/400 on missing visibility/ownership).
  - Latency budgets per request.
- **Optional third-party metrics:**
  - DeepEval GEval/AnswerRelevancy for groundedness and regression tracking.
  - Promptfoo `llm-rubric` for rubric-based grading or multilingual checks.

## Data & Seeding
- Use provided user credentials and doc IDs (Mexico/ARG corpus). Prefer attaching existing IDs; no re upload necessary.
- Conversations: namespace `local-smoke` or `eval`; tag runs with `agent-eval`.
- Keep content_hash uniqueness if new uploads are required; poll activation before tests.

## Execution & CI Hooks
- Markers: `agent_eval` for inclusion; `slow`/`longrun` for multi-turn or SSE checks; `requires_prod` to guard prod-only runs.
- Config: env file via `scripts/use_env.sh prod`; require `OPENAI_API_KEY` for judge; optional `VOYAGE_API_KEY` already required by service.
- Outputs: JSON/CSV summary per run; store judge rationales; optional promptfoo/deepeval artifacts in `artifacts/evals/`.
- CI: gated job that runs smoke subset (deterministic checks) and optionally judge-based metrics behind flag `RUN_JUDGE_EVALS=1`.

## Prompt Patterns (LLM-as-judge)
- Grounding check: provide question, model answer, retrieved chunks (text + doc id), expected doc IDs; ask judge to mark each claim as supported/unsupported and return pass/score plus offending claims.
- Citation check: for each `[c#]`, provide cited doc id and text span; ask judge to verify relevance and uniqueness.
- Style/format check: enforce concise answer + footnote formatting; reject if model adds extra PII or strays off-topic.

## Ops & Guardrails
- Cost: batch judge calls; cap per-test tokens; reuse conversation context for multi-turn cases.
- Retries: exponential backoff for judge/model calls; fail fast on auth/ingestion errors (no silent fallbacks).
- Logging: capture request/response payloads with PII scrubbing; include doc IDs and thread IDs in artifacts.
- Repro: store seed inputs, judge prompts, and model versions in run metadata.

## Next Steps
- Implement harness skeleton (`tests/evals/clients.py`, `fixtures.py`, `judges/llm_judge.py`, `scenarios/*`).
- Add sample scenarios (grounded summary, attachment gating failure, citation integrity) and wire to pytest markers.
- Add config for judge models and thresholds; document how to toggle Promptfoo/DeepEval integrations.
- Wire CI target for deterministic smoke + optional judge run; document `uv run pytest -m "agent_eval"`.
