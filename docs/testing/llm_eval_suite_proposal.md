# LLM Agent Eval Suite Design (OOP pytest, API-driven)

Design for a maintainable pytest harness that drives the Agent API end-to-end (chat + SSE, attachments, retrieval/rerank) against the production stack. All evals reuse the already uploaded `/home/nubol23/Desktop/Codes/MEX` and `/home/nubol23/Desktop/Codes/ARG` corpora tied to the provided eval user account (no new uploads), and every metric is judged by `gpt-5.1` with `reasoning.effort=high`. Evals load `.env.evals` by default (full copy of `.env.prod` but `AGENT_BASE_URL=http://localhost:8000` so they hit a local Agent API pointed at the prod DB/auth) and fail fast if any required secret is missing.

## Goals & Guardrails
- Real HTTP surface only: hit `/v1/conversations`, `/v1/conversations/{id}/attachments`, `/v1/chat` (blocking + SSE) with prod credentials; no DI overrides or stubs.
- Text-only ingestion path remains available, but the eval suite should reuse the already uploaded MEX/ARG documents on the provided eval user account; do not re-upload or flip ownership for these docs. Verify `status=active` for the known IDs before attaching.
- Advanced retrieval expectations: BM25 + pgvector with Voyage `voyage-context-3` + `rerank-2.5`, HyDE/HyPE rewrites, contextual headers, fusion diversity, strict `[c#]` citations.
- OOP-first pytest: scenario objects + thin client abstractions; fixtures manage env, auth, ingestion, and artifact sinks to minimize duplication.
- Metrics use maintained libraries (DeepEval, Ragas) plus deterministic checks; judges default to `gpt-5.1` with `reasoning.effort=high` and a single override knob.

## Seed Corpus (MEX/ARG) and Document IDs
- Reuse the prod-ingested PDFs under `/home/nubol23/Desktop/Codes/MEX` and `/home/nubol23/Desktop/Codes/ARG` that are already uploaded on the provided eval user (`eval_user@example.com`, `TestPass123!`). Do not re-upload these files; rely on the existing IDs and verify they are `status="active"`. Keep ownership on the eval user—no ownerless/base-scope clones.
- Expected active document set on the eval user (record in `datasets/shared_mex_arg.yaml` with content hashes):
  - Mexico Low income housing (Main report): `0510b240-5b88-4ae4-8678-4a21ac2ed102`
  - Mexico Low income housing (Vol 2): `be7724a0-d8a9-4304-b203-857cb79dce2c`
  - Financial Sector Assessment Program: `4d18a758-371e-4991-8f0f-bc9545395f4a`
  - Technical Note on Housing Finance: `a3f5776b-8a9e-4020-97d9-31a5b01f39f4`
  - Residential Energy Efficiency Programs: `bb8b657e-755d-46c5-a52f-e19d09145886`
  - Improving Housing Resilience Report: `09c2d186-35bf-44c4-9566-d71424587d0d`
  - FUNHAVIs housing microfinance program: `c729798f-d11c-4da8-b249-9d406d43ac19`
- Attach these documents to conversations for every scenario; do not re-upload unless recovery is required because an ID is missing/archived. Verify `status="active"` before running tests.

## Harness Architecture (OOP)
- **AgentApiClient**: wraps `httpx.AsyncClient` for the configured base URL; methods to mint HS256 JWT (`AUTH_SHARED_SECRET`), create conversations, bulk-attach docs, send chat (blocking/SSE), and parse citations/latency from responses. SSE helper exists but streaming tests are currently skipped in pytest to avoid duplicate artifacts while we focus on blocking evals.
- **Scenario Models (Pydantic v2)**: typed dataclasses to compose pytest parametrization and reuse across suites:
  - `AttachmentSpec`: `document_id`, `country_code`, `visibility`, `role`, `access_scope` (default `base`).
  - `Turn`: `role`, `content`, `attachments`, `expectations` (optional rubrics), `response_mode` (blocking/stream).
  - `MetricSpec`: enum for `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`, `citation_coverage`, `latency_budget`, `rerank_ordering`, `toxicity` with thresholds + optional judge override.
  - `EvalScenario`: name, description, tags, `constraints` (country_code, auto_attach_base_docs), corpus (`AttachmentSpec` list), ordered `turns`, metric plan, expected rerank filters (HyDE/fusion flags), SSE expectation (stream vs blocking).
  - `EvalRunConfig`: base URL, `EVAL_USER_ID`, JWT secret, judge model (default `gpt-5.1`), reasoning effort (`high`), artifact dir, timeouts, retry/backoff.
- **EvalRunner**: orchestrates one scenario—creates conversation, bulk-attaches docs, executes turns, captures telemetry (latency, citations, retrieved chunk IDs/scores if returned), runs metric evaluators, and writes artifacts. Supports `stateless=False` by default to exercise persistence. Composes scenario steps into pytest-friendly objects to allow reuse in multiple test modules.
- **Metrics Layer**:
  - DeepEval GEval for `faithfulness` and `answer_relevancy` using `gpt-5.1` judge (reasoning.effort=high) with scenario-specific thresholds.
  - Ragas `context_precision`/`context_recall` fed with retrieved chunks/citations, aligning judges via the Ragas alignment guide.
  - Deterministic: citation coverage (% sentences with `[c#]`), rerank monotonicity (scores non-increasing), latency budget per turn, attachment gating assertions (non-active docs must fail).
- **Artifacts**: JSON per run under `services/agent-api/tests/evals/artifacts/<timestamp>_<scenario>.json` (gitignored) capturing prompts, responses, retrieval traces, metric scores, and judge rationales (flat structure to simplify collection).

## Pytest Layout & Fixtures
```
services/agent-api/tests/evals/
  conftest.py           # env/marker config, artifact dir fixture, judge client fixture
  core/
    client.py           # AgentApiClient (HTTP + SSE helpers)
    scenarios.py        # Pydantic models + loaders (YAML/JSON)
    runner.py           # EvalRunner orchestrating chat + metrics
    metrics.py          # DeepEval + Ragas adapters + deterministic checks
    judges.py           # judge config (gpt-5.1 reasoning.effort=high default)
    telemetry.py        # helpers to parse citations/chunks/latency from responses
  datasets/
    shared_mex_arg.yaml # canonical doc IDs/content_hashes + scenarios
    stress/*.yaml       # high-recall, hyde/fusion, pyodide, attachment-gating cases
  test_scenarios.py     # parametrized pytest entrypoint (marks=eval,eval_api,eval_sse)
  artifacts/            # gitignored outputs
```
- **Fixtures**:
  - `eval_env`: validates `AGENT_BASE_URL`, `AUTH_SHARED_SECRET`, `EVAL_USER_ID`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, `INGEST_BASE_URL`; skips with clear reason if missing. Also checks that required doc IDs from `shared_mex_arg.yaml` are present/active.
  - `agent_client`: initialized `AgentApiClient` with signed JWT for `EVAL_USER_ID`; exposes helpers for blocking and SSE chat modes plus attachment helpers.
  - `ingested_docs`: verifies/loads the MEX/ARG doc metadata for the eval user and returns IDs + content hashes for scenarios; avoid re-upload and fail/skip if required docs are inactive or missing.
  - `scenario_catalog`: loads YAML scenarios into `EvalScenario` objects for parametrization; supports tagging (e.g., `eval_api`, `eval_sse`, `eval_pyodide`, `eval_heavy`).
  - `artifact_writer`: writes run artifacts to timestamped directory; respects `EVAL_ARTIFACTS_DIR` and annotates runs with scenario metadata and doc IDs.

## MEX/ARG Corpora Usage (prod-only, no re-upload)
- Files already reside in the eval user account; confirm availability via `/v1/documents` with the provided credentials before runs.
- Treat the listed doc IDs as canonical; attach them to conversations using the eval user token. Do not trigger new uploads for these corpora. If a doc is missing/archived, prefer restoring access for the eval user rather than creating a new ownerless/base-scoped copy; only ingest new material when adding new scenarios outside the MEX/ARG set.

## Scenario Coverage (examples)
- **Hybrid retrieval + HyDE/HyPE**: long-form policy questions spanning multiple MEX/ARG memos; assert rerank scores drop monotonically and Ragas recall passes threshold.
- **Attachment gating**: attempt chat with non-active doc ID → expect 409; then re-run with active doc → success.
- **SSE streaming**: run `response_mode=stream`, ensure tokens arrive in order and final `done` frame contains citations/latency.
- **Citation strictness**: numeric questions (e.g., finance metrics) must include `[c#]` markers and DeepEval faithfulness > threshold.
- **Pyodide tool**: dataset question requiring tabular calc; assert tool call present and answer relevancy >= threshold. Uses the vendored Deno-based Pyodide sandbox (no remote base URL or package fallback).
- **Ownership/access**: docs owned by the eval user attach and answer; docs owned by other users should be rejected or hidden when attempting attachment/chat.

## Metrics & Judge Configuration
- **Judge**: default `model="gpt-5.1"` with `reasoning.effort="high"` on every metric call; override via `EVAL_JUDGE_MODEL` for experiments. Aligns with LLM-as-judge best practices from Evidently and Ragas (prompt clarity, role hints). Apply the same judge defaults to SSE and blocking paths to keep metrics comparable across transport modes.
- **DeepEval**: use GEval templates for `faithfulness` and `answer_relevancy` (per https://deepeval.com/docs/metrics-faithfulness); thresholds suggested start at `>=0.8` faithfulness, `>=0.75` answer relevancy.
- **Ragas**: `context_precision` and `context_recall` (per https://docs.ragas.io/en/stable/howtos/applications/align-llm-as-judge/) computed from retrieved chunks/citations; thresholds tuned per scenario (e.g., precision >=0.6, recall >=0.5 for long docs).
- **Deterministic checks**: citation coverage >=90% of sentences have `[c#]`; rerank ordering non-increasing; latency budgets per scenario (e.g., <12s total, <4s streaming first token). Qdrant’s RAG eval guide informs recall/latency focus (https://qdrant.tech/blog/rag-evaluation-guide/).
- **Toxicity/safety**: optional DeepEval toxicity metric for open-ended prompts; default threshold high (<=0.1 risk score).

## Pytest Markers, Commands, CI
- Markers: `@pytest.mark.eval` for all evals, `eval_api` for HTTP blocking, `eval_sse` for streaming (currently skipped), `eval_pyodide` for tool-heavy, `eval_heavy` for longer latency. Add `requires_prod` to guard prod-only runs (default).
- Commands:
  - Local Agent API with prod DB/auth (preferred for eval dev): `set -a && source .env.evals && set +a && cd services/agent-api && uv run pytest tests/evals -m eval --maxfail=1`
  - Prod via compose pointing to prod DB: `COMPOSE_PROFILES=reduced,ops docker compose --env-file .env.prod up agent-api auth-service user-service ingestion-service -d` then `cd services/agent-api && uv run pytest tests/evals -m eval --maxfail=1`; tear down compose after runs.
  - Stream focus (when re-enabled): `uv run pytest tests/evals -m "eval_sse" --disable-warnings -q`
- CI integration: optional nightly job that exports required env secrets, runs `-m eval_api and not eval_heavy`, uploads artifacts as workflow artifacts; skips gracefully when env vars missing.
- Gitignore `services/agent-api/tests/evals/artifacts/` and DeepEval caches; artifacts stored locally only.

## Environment Loading & Fail-Fast Defaults
- `.env.evals` mirrors `.env.prod` but sets `AGENT_BASE_URL=http://localhost:8000` so evals can drive a local Agent API against the prod DB/auth; loader requires `.env.evals` (no fallback). Required: `AGENT_BASE_URL`, `AUTH_BASE_URL`, `EVAL_USER_EMAIL`, `EVAL_USER_PASSWORD`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, and Deno path exports (`DENO_INSTALL` and `PATH=${DENO_INSTALL}/bin:${PATH}`) for the vendored sandbox.
- No fallbacks to templated URLs or missing secrets; OpenAI/Voyage keys must be present (fail fast).

## Implementation Notes
- Reuse shared data layer types for document IDs/owner representations; never craft raw SQL.
- Keep retries minimal (e.g., backoff on 429/5xx from Agent API/OpenAI) and fail fast otherwise.
- Scenario definitions stay declarative (YAML/JSON) but load into OOP models for reuse inside tests.
- Use `auto_attach_base_docs=True` where appropriate to exercise built-in base corpus handling; otherwise explicitly set attachments per turn.

## References
- LLM-as-judge patterns and prompt design: https://www.evidentlyai.com/llm-guide/llm-as-a-judge
- Ragas judge alignment + retrieval metrics: https://docs.ragas.io/en/stable/howtos/applications/align-llm-as-judge/
- DeepEval faithfulness/relevancy metrics: https://deepeval.com/docs/metrics-faithfulness
- Pytest fixture/factory best practices: https://docs.pytest.org/en/stable/how-to/fixtures.html
- RAG eval best practices (recall/latency emphasis): https://qdrant.tech/blog/rag-evaluation-guide/
