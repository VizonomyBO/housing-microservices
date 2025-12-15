# Task: Implement LLM Agent Eval Suite (pytest, FastAPI DI, GPT-5.1 judge)

This brief is for a fresh coding agent. Follow `AGENTS.md` (root and `services/agent-api/AGENTS.md`) and keep the memory bank/docs in sync. Key context lives in `docs/testing/llm_eval_suite_proposal.md`.

## Scope
- Build a pytest-driven eval harness under `services/agent-api/tests/evals` using OOP scenario models, FastAPI dependency overrides, and LLM-as-judge metrics.
- Use real FastAPI endpoints in test mode (no Docker), bypass auth via DI, and enforce read-only behavior (stateless chats, read-only DB session, no event persistence).
- Attach existing documents (from AWS/DB), allow conversation history, capture retrieval traces, and dump eval artifacts to JSON (gitignored).
- Judge defaults: GPT-5.1 reasoning-medium for CI gating; GPT-4o-mini for local dev; allow swapping in Claude 3.5/Bedrock via config. Avoid LangSmith remote execution/caching; prefer local cache.

## Current Harness Snapshot (added in this task)
- New package at `services/agent-api/tests/evals/` with `core/` modules (`scenarios.py`, `runner.py`, `metrics.py`, `judges.py`, `telemetry.py`), sample dataset (`datasets/housing_basics.yaml`), and pytest entrypoint (`test_scenarios.py`).
- Real API + data: Runner now hits the live Agent API (`AGENT_BASE_URL`) with HS256 tokens minted from `AUTH_SHARED_SECRET`, creates conversations via `/v1/conversations`, bulk-attaches docs, and posts `/v1/chat` with `allow_stateless=false` (no stubs). Required env: `source .env.prod` and set `EVAL_USER_ID=11111111-2222-3333-4444-555555555555`.
- Real documents: Prod-seeded reduced E2E docs are attached in every scenario: `doc_policy` (`fb400d68-3200-4e07-9231-cea9ee7163eb`), `doc_ledger` (`6806e86f-549f-4588-84de-2dd089a8f7da`), and `doc_kpi` (`232d5d61-f083-448f-ae2f-2aa9b9a1a3c0`). Content comes from `services/agent-api/tests/data/reduced_e2e/*.md`.
- Metrics: DeepEval GEval (faithfulness/relevance) + Ragas (context precision/recall) + deterministic checks (citations). Judge default is GPT-5.1 reasoning-medium for all metrics; OPENAI_API_KEY is required.
- Artifacts: JSON dumped under `services/agent-api/tests/evals/artifacts/evals/<ts>/<scenario>/result.json` (gitignored). Override with `EVAL_ARTIFACTS_DIR=<path>` when needed.
- Execution: `cd services/agent-api && uv run pytest tests/evals -m eval` (requires `.env.prod`, AUTH_SHARED_SECRET/OPENAI_API_KEY, network to prod + OpenAI). Artifacts written automatically via `EvalResult.write_artifacts()`.
- Smoke prompt coverage: `datasets/reduced_e2e_smoke.yaml` mirrors reduced E2E prompts (policy guardrails, District 9 cross-doc plan, ledger aggregate, KPI trigger) and reuses the prod docs above. `housing_basics.yaml` now points to the same policy memo with stricter prompt wording.

## References
- Process: `AGENTS.md`, `services/agent-api/AGENTS.md`.
- Design: `docs/testing/llm_eval_suite_proposal.md`.
- Testing patterns: `services/agent-api/tests` layout; run commands via `uv`.
- Data/ingestion context: `docs/agents/implementation.md`, `docs/agents/rag_blueprint.md`.

## Deliverables
- New `services/agent-api/tests/evals` package with core modules, sample dataset(s), pytest entry, and gitignored `artifacts/evals/`.
- Dependency wiring for DI overrides (auth bypass, stateless chat flag, read-only DB session, no-op conversation store, retrieval telemetry sink).
- Metrics integration (Ragas + DeepEval + custom deterministic checks) with GPT-5.1 reasoning-medium default judge.
- Example scenarios referencing existing documents and conversation turns.
- Documentation updates if harness choices deviate from the proposal.

## Subtasks & Steps (track progress per subtask)

1) **Scaffold & Config**
   - [ ] Create `services/agent-api/tests/evals/core` modules (`scenarios.py`, `runner.py`, `metrics.py`, `judges.py`, `telemetry.py`) and `datasets/` + `artifacts/` (gitignored).
   - [ ] Add pytest marker (e.g., `eval`) and sample `test_scenarios.py` parametrization.
   - [ ] Update gitignore for `artifacts/evals/`.

2) **Dependency Overrides (FastAPI)**
   - [ ] Add fixture to build app with auth stub + `allow_stateless=true`.
   - [ ] Inject read-only SQLAlchemy session (`SET default_transaction_read_only=on` or read-replica DSN).
   - [ ] Swap conversation/event persistence to in-memory/no-op.
   - [ ] Provide retrieval telemetry sink that captures chunk IDs/scores/latency returned to the harness.

3) **Scenarios & Data Hooks**
   - [ ] Implement Pydantic models (`DocRef`, `Turn`, `Expectation`, `MetricSpec`, `EvalScenario`, `EvalRunConfig`) with YAML loader.
   - [ ] Provide helper to reference existing doc IDs/versions without re-uploading; support attachment and prior history on `/v1/chat`.
   - [ ] Add sample dataset(s) (`housing_basics.yaml`, etc.) with doc refs and expectations.

4) **Metrics & Judges**
   - [ ] Integrate Ragas metrics (context precision/recall, answer relevance, faithfulness) using retrieved chunks.
   - [ ] Integrate DeepEval metrics (GEval rubric-based faithfulness/correctness, toxicity, coherence) with judge default GPT-5.1 reasoning-medium; allow override per scenario.
   - [ ] Add deterministic checks (latency budget, citation coverage, empty-context guard) and local judge-call caching.

5) **Artifacts & Safety**
   - [ ] Ensure runs write JSON artifacts under `artifacts/evals/<ts>/` (inputs, outputs, retrieval traces, metric scores, judge transcripts).
   - [ ] Confirm no DB writes (stateless chat, read-only session, no-op persistence, analytics disabled).

6) **Docs & Verification**
   - [ ] Update `docs/testing/llm_eval_suite_proposal.md` if implementation diverges.
   - [ ] Run `uv run pytest tests/evals -m eval` (and format/lint commands from `AGENTS.md` if code added). Artifacts auto-write to `services/agent-api/tests/evals/artifacts/evals/`.
   - [ ] Summarize commands/results in final response; keep plan/tracker lifecycle per `AGENTS.md`.
