# Task: Implement LLM Agent Eval Suite (pytest, real Agent API, GPT-5.1 + reasoning.effort)

This brief is for a fresh coding agent. Follow `AGENTS.md` (root and `services/agent-api/AGENTS.md`) and keep the memory bank/docs in sync. Key context lives in `docs/testing/llm_eval_suite_proposal.md`.

## Scope
- Build and maintain a pytest-driven eval harness under `services/agent-api/tests/evals` using typed scenario models and LLM-as-judge metrics.
- Always hit the real Agent API using production credentials from `.env.prod`; no stubs, fixtures, or mocking. Conversations and attachments are created via real endpoints with HS256 tokens minted from `AUTH_SHARED_SECRET`.
- Reuse the prod-seeded reduced E2E documents (policy, ledger, KPI) instead of uploading new ones; attach them in every scenario and capture retrieval traces.
- Use GPT-based judges for all rubric metrics (default `gpt-5.1` with `reasoning.effort=medium`, override via `EVAL_JUDGE_MODEL`) and keep the metric stack limited to DeepEval GEval + Ragas context metrics plus deterministic checks.
- Dump eval artifacts to JSON (gitignored), and treat thresholds as gates for smoke coverage rather than perf benchmarking.

## Current Harness Snapshot (added in this task)
- Package layout: `services/agent-api/tests/evals/core/` (`scenarios.py`, `runner.py`, `metrics.py`, `judges.py`, `telemetry.py`), datasets under `datasets/`, pytest entrypoint `test_scenarios.py`, gitignored `artifacts/evals/`.
- Real API + data: Runner uses `AGENT_BASE_URL` and a minted JWT (HS256) to call `/v1/conversations`, bulk-attach docs, and post `/v1/chat` with `allow_stateless=false`. Required env: `source .env.prod`, set `EVAL_USER_ID=11111111-2222-3333-4444-555555555555`, and provide `OPENAI_API_KEY`.
- Real documents: Attach prod doc IDs for reduced E2E smoke—policy `fb400d68-3200-4e07-9231-cea9ee7163eb`, ledger `6806e86f-549f-4588-84de-2dd089a8f7da`, KPI `232d5d61-f083-448f-ae2f-2aa9b9a1a3c0`—with content mirrors under `services/agent-api/tests/data/reduced_e2e/*.md`.
- Metrics: DeepEval GEval for `faithfulness`/`answer_relevance`, Ragas for `context_precision`/`context_recall`, deterministic `citation_coverage` + `latency`. Judge default is `gpt-5.1` with `reasoning.effort=medium`; override via `EVAL_JUDGE_MODEL`. OPENAI_API_KEY is mandatory; no stubbed judges.
- Artifacts: JSON dumped under `services/agent-api/tests/evals/artifacts/evals/<ts>/<scenario>/result.json` (gitignored). Override with `EVAL_ARTIFACTS_DIR=<path>` when needed.
- Execution: `cd services/agent-api && uv run pytest tests/evals -m eval` (requires `.env.prod`, AUTH_SHARED_SECRET/OPENAI_API_KEY, network to prod + OpenAI). Artifacts written automatically via `EvalResult.write_artifacts()`.
- Smoke prompt coverage: `datasets/reduced_e2e_smoke.yaml` mirrors reduced E2E prompts (policy guardrails, District 9 cross-doc plan, ledger aggregate, KPI trigger) and reuses the prod docs above. `housing_basics.yaml` targets the policy memo.

## References
- Process: `AGENTS.md`, `services/agent-api/AGENTS.md`.
- Design: `docs/testing/llm_eval_suite_proposal.md`.
- Testing patterns: `services/agent-api/tests` layout; run commands via `uv`.
- Data/ingestion context: `docs/agents/implementation.md`, `docs/agents/rag_blueprint.md`.

## Deliverables
- `services/agent-api/tests/evals` package with real-API runner, datasets, pytest entry, and gitignored `artifacts/evals/`.
- Dependency wiring for live API usage (HS256 auth minting, real conversations/attachments, retrieval telemetry capture).
- Metrics integration (Ragas + DeepEval + custom deterministic checks) with `gpt-5.1` default judge (reasoning.effort=medium) and env override.
- Example scenarios referencing existing production documents and conversation turns.
- Documentation updates if harness choices change.

## Subtasks & Steps (track progress per subtask)

1) **Scaffold & Config**
   - [ ] Keep `services/agent-api/tests/evals/core` modules (`scenarios.py`, `runner.py`, `metrics.py`, `judges.py`, `telemetry.py`) and `datasets/` + `artifacts/` (gitignored) in sync with design.
   - [ ] Ensure pytest marker `eval` and `test_scenarios.py` parametrization stay current.
   - [ ] Keep gitignore entries for `artifacts/evals/` and DeepEval caches.

2) **Real API Execution (no stubs)**
   - [ ] Always call the live Agent API via `AGENT_BASE_URL` with HS256 tokens from `AUTH_SHARED_SECRET`; disable any DI/auth bypass.
   - [ ] Attach existing doc IDs instead of uploading; ensure `allow_stateless=false` and telemetry is captured from real responses.

3) **Scenarios & Data Hooks**
   - [ ] Maintain Pydantic models (`DocRef`, `Turn`, `Expectation`, `MetricSpec`, `EvalScenario`, `EvalRunConfig`) with YAML loader.
   - [ ] Keep dataset YAMLs aligned with seeded prod doc IDs and local content mirrors.

4) **Metrics & Judges**
   - [ ] Keep Ragas metrics (context precision/recall) and DeepEval GEval rubrics (faithfulness/relevance) wired to real judges.
   - [ ] Default judge remains `gpt-5.1` with `reasoning.effort=medium`; allow override via `EVAL_JUDGE_MODEL`; no stub/local judges.
   - [ ] Keep deterministic checks (citation coverage, latency) alongside metric thresholds tuned for smoke gating.

5) **Artifacts & Safety**
   - [ ] Ensure runs write JSON artifacts under `artifacts/evals/<ts>/` (inputs, outputs, retrieval traces, metric scores, judge transcripts).
   - [ ] Keep gitignore entries so artifacts stay out of version control.

6) **Docs & Verification**
   - [ ] Update `docs/testing/llm_eval_suite_proposal.md` when the harness changes.
   - [ ] Run `uv run pytest tests/evals -m eval` after sourcing `.env.prod`; artifacts auto-write to `services/agent-api/tests/evals/artifacts/evals/`.
   - [ ] Summarize commands/results in final responses; keep plan/tracker lifecycle per `AGENTS.md`.
