# LLM Agent Eval Suite Design (OOP pytest, API-driven)

Design for a maintainable pytest harness that drives the Agent API end-to-end (chat + SSE, attachments, retrieval/rerank) against the production stack. All evals ingest and use the `/home/nubol23/Desktop/Codes/MEX` and `/home/nubol23/Desktop/Codes/ARG` corpora as shared documents (no owner), and every metric is judged by `gpt-5.1` with `reasoning.effort=high`.

## Goals & Guardrails
- Real HTTP surface only: hit `/v1/conversations`, `/v1/conversations/{id}/attachments`, `/v1/chat` (blocking + SSE) with prod credentials; no DI overrides or stubs.
- Text-only ingestion path: ingest MEX/ARG PDFs through ingestion-service (`/v1/documents/upload` → `/v1/documents/upload/complete`) with `owner_user_id=""`/`access_scope="base"` so docs are shareable; verify `status=active` before attaching.
- Advanced retrieval expectations: BM25 + pgvector with Voyage `voyage-context-3` + `rerank-2.5`, HyDE/HyPE rewrites, contextual headers, fusion diversity, strict `[c#]` citations.
- OOP-first pytest: scenario objects + thin client abstractions; fixtures manage env, auth, ingestion, and artifact sinks to minimize duplication.
- Metrics use maintained libraries (DeepEval, Ragas) plus deterministic checks; judges default to `gpt-5.1` with `reasoning.effort=high` and a single override knob.

## Harness Architecture (OOP)
- **AgentApiClient**: wraps `httpx.AsyncClient` for prod base URL; methods to mint HS256 JWT (`AUTH_SHARED_SECRET`), create conversations, bulk-attach docs, send chat (blocking/SSE), and parse citations/latency from responses. SSE helper buffers events for metric use.
- **Scenario Models (Pydantic v2)**:
  - `AttachmentSpec`: `document_id`, `country_code`, `visibility`, `role`, `access_scope` (default `base`).
  - `Turn`: `role`, `content`, `attachments`, `expectations` (optional rubrics), `response_mode` (blocking/stream).
  - `MetricSpec`: enum for `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`, `citation_coverage`, `latency_budget`, `rerank_ordering`, `toxicity` with thresholds + optional judge override.
  - `EvalScenario`: name, description, tags, `constraints` (country_code, auto_attach_base_docs), corpus (`AttachmentSpec` list), ordered `turns`, metric plan, expected rerank filters (HyDE/fusion flags), SSE expectation (stream vs blocking).
  - `EvalRunConfig`: base URL, `EVAL_USER_ID`, JWT secret, judge model (default `gpt-5.1`), reasoning effort (`high`), artifact dir, timeouts, retry/backoff.
- **EvalRunner**: orchestrates one scenario—creates conversation, bulk-attaches docs, executes turns, captures telemetry (latency, citations, retrieved chunk IDs/scores if returned), runs metric evaluators, and writes artifacts. Supports `stateless=False` by default to exercise persistence.
- **Metrics Layer**:
  - DeepEval GEval for `faithfulness` and `answer_relevancy` using `gpt-5.1` judge (reasoning.effort=high) with scenario-specific thresholds.
  - Ragas `context_precision`/`context_recall` fed with retrieved chunks/citations, aligning judges via the Ragas alignment guide.
  - Deterministic: citation coverage (% sentences with `[c#]`), rerank monotonicity (scores non-increasing), latency budget per turn, attachment gating assertions (non-active docs must fail).
- **Artifacts**: JSON per run under `services/agent-api/tests/evals/artifacts/<ts>/<scenario>/` (gitignored) capturing prompts, responses, SSE transcript, retrieval traces, metric scores, and judge rationales.

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
  - `eval_env`: validates `AGENT_BASE_URL`, `AUTH_SHARED_SECRET`, `EVAL_USER_ID`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, `INGEST_BASE_URL`; skips with clear reason if missing.
  - `agent_client`: initialized `AgentApiClient` with signed JWT for `EVAL_USER_ID`.
  - `ingested_docs`: seeds/refreshes MEX/ARG via ingestion (see below), returns IDs + content hashes for scenarios.
  - `scenario_catalog`: loads YAML scenarios into `EvalScenario` objects for parametrization.
  - `artifact_writer`: writes run artifacts to timestamped directory; respects `EVAL_ARTIFACTS_DIR`.

## MEX/ARG Corpora Ingestion (prod-only, shared)
- Files: `/home/nubol23/Desktop/Codes/MEX/*.pdf`, `/home/nubol23/Desktop/Codes/ARG/*.pdf`.
- Flow (per ingestion-service):
  1. `POST /v1/documents/upload` with JSON: `document_name`, `source_type="pdf"`, `access_scope="base"`, `owner_user_id=""`, `file_size_bytes`, `country_code` (`MEX`/`ARG`), `language="en"`, optional `tags` (`["eval","shared"]`), `output_dimension` (match pgvector, default 1024). Auth via ingestion bearer (HS256, see `ingestion_service.auth`).
  2. Receive `upload.url` + signed form fields; `owner_user_id` stays blank (maps to shared/system owner).
  3. `POST upload.url` multipart with the PDF file and returned fields. On success, expect `status="active"` and `content_hash`.
  4. Verify via Agent API `GET /v1/documents?content_hash=...` and record `document_id` + `content_hash` in `datasets/shared_mex_arg.yaml`.
- Treat uploads as idempotent via `content_hash`; if deduped, reuse returned IDs. Ingest once, reuse for all eval scenarios.

## Scenario Coverage (examples)
- **Hybrid retrieval + HyDE/HyPE**: long-form policy questions spanning multiple MEX/ARG memos; assert rerank scores drop monotonically and Ragas recall passes threshold.
- **Attachment gating**: attempt chat with non-active doc ID → expect 409; then re-run with active doc → success.
- **SSE streaming**: run `response_mode=stream`, ensure tokens arrive in order and final `done` frame contains citations/latency.
- **Citation strictness**: numeric questions (e.g., finance metrics) must include `[c#]` markers and DeepEval faithfulness > threshold.
- **Pyodide tool**: dataset question requiring tabular calc; assert tool call present and answer relevancy >= threshold.
- **Ownership/null owner**: shared docs (owner=None/`SYSTEM_OWNER_SENTINEL`) attach and answer; per-user doc should be skipped when thread owner differs.

## Metrics & Judge Configuration
- **Judge**: default `model="gpt-5.1"` with `reasoning.effort="high"` on every metric call; override via `EVAL_JUDGE_MODEL` for experiments. Aligns with LLM-as-judge best practices from Evidently and Ragas (prompt clarity, role hints).
- **DeepEval**: use GEval templates for `faithfulness` and `answer_relevancy` (per https://deepeval.com/docs/metrics-faithfulness); thresholds suggested start at `>=0.8` faithfulness, `>=0.75` answer relevancy.
- **Ragas**: `context_precision` and `context_recall` (per https://docs.ragas.io/en/stable/howtos/applications/align-llm-as-judge/) computed from retrieved chunks/citations; thresholds tuned per scenario (e.g., precision >=0.6, recall >=0.5 for long docs).
- **Deterministic checks**: citation coverage >=90% of sentences have `[c#]`; rerank ordering non-increasing; latency budgets per scenario (e.g., <12s total, <4s streaming first token). Qdrant’s RAG eval guide informs recall/latency focus (https://qdrant.tech/blog/rag-evaluation-guide/).
- **Toxicity/safety**: optional DeepEval toxicity metric for open-ended prompts; default threshold high (<=0.1 risk score).

## Pytest Markers, Commands, CI
- Markers: `@pytest.mark.eval` for all evals, `eval_api` for HTTP blocking, `eval_sse` for streaming, `eval_pyodide` for tool-heavy, `eval_heavy` for longer latency.
- Commands:
  - Local/prod: `cd services/agent-api && uv run pytest tests/evals -m eval --maxfail=1`
  - Stream focus: `uv run pytest tests/evals -m "eval_sse" --disable-warnings -q`
- CI integration: optional nightly job that exports required env secrets, runs `-m eval_api and not eval_heavy`, uploads artifacts as workflow artifacts; skips gracefully when env vars missing.
- Gitignore `services/agent-api/tests/evals/artifacts/` and DeepEval caches; artifacts stored locally only.

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
