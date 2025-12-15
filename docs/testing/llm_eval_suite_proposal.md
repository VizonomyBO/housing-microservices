# LLM Agent Eval Suite Proposal

## Goals & Constraints
- Type-safe, OOP-first eval scenarios runnable via `uv run pytest`, not bespoke CLIs.
- Exercise the real FastAPI endpoints (no Docker required) with dependency overrides to bypass auth while keeping downstream components intact.
- Attach existing documents stored in AWS Postgres/S3, load conversation history, and evaluate responses with LLM-as-judge metrics.
- Capture retrieval traces (chunk IDs, scores, latency) for metrics without persisting conversations/events to production DB; write eval artifacts to JSON under `artifacts/evals/`.
- Read from prod data sources in test mode, but prevent writes (stateless chat, read-only DB user/transactions, in-memory conversation store).
- Enable extensible metric stacks (faithfulness, answer/context relevance, toxicity, latency, grounding) and judge models (default GPT-5.1 reasoning-medium) with cheap/local fallbacks.

## Recommended Stack (grounded in research)
- **DeepEval** for pytest-friendly LLM-as-judge metrics and typed test cases (30+ metrics, supports component/e2e eval) [deepeval docs](https://deepeval.com/docs/getting-started).
- **Ragas** for retrieval-oriented metrics (faithfulness, answer relevancy, context precision/recall) with pytest CI mode [ragas pytest guide](https://docs.ragas.io/en/v0.3.0/howtos/applications/add_to_ci/).
- **TruLens RAG triad** (context relevance, groundedness, answer relevance) as a conceptual baseline for custom metrics [trulens RAG triad](https://www.trulens.org/getting_started/core_concepts/rag_triad/).
- **Judge models**: Default to **GPT-5.1 reasoning-medium** for gating; use GPT-4o-mini for fast dev iterations; allow Claude 3.5 Sonnet or Bedrock/Vertex models via DeepEval custom LLM adapter. Benchmarks show GPT-4-class and Claude 3.5-class models perform well as judges [LLM judge survey](https://galtea.ai/blog/exploring-state-of-the-art-llms-as-judges).

## Proposed Architecture & Abstractions
- **Type-safe scenario models (Pydantic v2)**:
  - `DocRef`: `{doc_id: UUID, version_id: str | None, title: str}` representing existing DB/S3 documents to attach.
  - `Turn`: `{role: Literal["user","assistant"], content: str, attachments: list[DocRef] | None}` for multi-turn histories.
  - `Expectation`: `{label: str, rubric: str, expected_answer: str | None, citations_required: bool}`.
  - `MetricSpec`: enum of built-in metrics (`faithfulness`, `context_precision`, `answer_relevancy`, `toxicity`, `latency`, etc.) with optional thresholds and judge model.
  - `EvalScenario`: name, description, tenant/scope, dataset tag, `turns`, `expectations`, `metric_specs`, optional seeds for reproducibility.
  - `EvalRunConfig`: judge model defaults, OpenAI/Anthropic keys, `stateless=True`, `capture_retrieval=True`, `read_only_db=True`, output path.
- **Execution harness (pytest fixtures + FastAPI TestClient)**:
  - Fixture spins up the FastAPI app via the existing app factory, overrides auth dependency to a stub user, overrides conversation repo with an in-memory null sink, and injects a **read-only** SQLAlchemy session (`options="-c default_transaction_read_only=on"` or read-replica DSN).
  - Use `allow_stateless=true` on `/v1/chat` requests and disable analytics/event emitters via dependency overrides.
  - Attach documents by calling the real upload/attach endpoints with `dry_run=true` (if available) or a dedicated `EvalAttachmentService` override that fetches documents by `doc_id` without writing new rows.
  - Capture retrieval data by enabling a debug flag or injecting an `EvalTelemetrySink` dependency that subscribes to retrieval events (chunk IDs, scores, reranker outputs, elapsed ms) and returns them with the response for metric computation.
- **Metric layer**:
  - Ragas metrics for retrieval quality: context precision/recall, answer relevance, faithfulness using retrieved chunks vs. answer.
  - DeepEval metrics for factuality/hallucination, toxicity, coherence, and custom GEval rubrics per `Expectation`.
  - Custom deterministic metrics: latency budgets, citation coverage (% of sentences with citations), empty-context guard.
  - Support per-scenario thresholds and judge model overrides; default to GPT-5.1 reasoning-medium for CI gating, GPT-4o-mini for local dev.
- **Result handling**:
  - Write `artifacts/evals/<timestamp>/<scenario>.json` containing input turns, retrieved chunks (IDs and text hashes), raw model outputs, metric scores, and LLM judge transcripts.
  - Optionally emit a single merged `summary.json` for dashboards; never write to application DB.

## Filesystem Layout (proposed)
```
services/agent-api/tests/evals/
  core/
    scenarios.py        # Pydantic models + loader
    runner.py           # Pytest fixtures, FastAPI TestClient setup, dependency overrides
    metrics.py          # Ragas + DeepEval adapters, custom metrics
    judges.py           # Judge model selection/config (OpenAI/Anthropic/local)
    telemetry.py        # Retrieval trace sink + helpers
  datasets/
    housing_basics.yaml     # Scenario definitions (docs, turns, expectations)
    troubleshooting.yaml
  artifacts/             # gitignored JSON outputs per run
  test_scenarios.py      # Parametrized pytest using Scenario objects
```
- Keep proposal doc here: `docs/testing/llm_eval_suite_proposal.md`.

## Example Flow (pytest)
```python
# services/agent-api/tests/evals/test_scenarios.py
import pytest
from .core.runner import EvalRunner
from .core.scenarios import load_scenarios

runner = EvalRunner()

@pytest.mark.parametrize("scenario", load_scenarios("datasets/housing_basics.yaml"))
def test_eval_scenario(scenario):
    result = runner.run(scenario)
    result.assert_thresholds()  # raises if any metric falls below spec
    result.write_artifacts()    # dumps JSON locally
```
- `EvalRunner.run`:
  1) Spins FastAPI app with DI overrides (`stateless`, auth bypass, read-only session).
  2) Builds conversation history + attachments from `Scenario`.
  3) Calls `/v1/chat` (and upload/attach endpoints if required) against the local app.
  4) Captures retrieval traces via `EvalTelemetrySink`.
  5) Evaluates metrics (Ragas/DeepEval/custom) and returns a typed `EvalResult`.

## Data Safety (read prod, do not write)
- Use a dedicated read-only DB role or per-connection `SET default_transaction_read_only = on`; enforce in the SQLAlchemy session override.
- Always send `allow_stateless=true` to skip persistence; override conversation storage to a no-op adapter to guarantee no writes.
- Disable analytics/observability exporters during eval runs to avoid noisy prod telemetry.
- Avoid re-uploading docs; reference existing `doc_id`/`version_id` via `DocRef` or use `dry_run` attachment endpoints that do not persist.
- Store all eval outputs under `artifacts/evals/` (gitignored) and keep LLM judge transcripts out of the DB.

## Metrics & Judges
- **Retrieval**: context precision/recall, answer relevance, groundedness (TruLens triad), chunk coverage (% of cited chunks).
- **Response quality**: faithfulness/hallucination (GEval/DeepEval), fluency/coherence, safety/toxicity.
- **Operational**: latency budgets per scenario, token/price accounting, fallback/dedupe detection.
- **Judges**: default GPT-5.1 reasoning-medium for CI gating; GPT-4o-mini for dev; allow config for Claude 3.5 or Bedrock/Vertex models. Cache judge calls via local file cache to stabilize CI (avoid remote LangSmith caching for now).

## Execution Commands (proposed)
- Local dev: `cd services/agent-api && uv run pytest tests/evals -m eval --maxfail=1`
- Record artifacts only: `EVAL_ARTIFACTS_DIR=artifacts/evals/$(date +%s) uv run pytest tests/evals -m eval --disable-warnings -q`

## Current Eval Suite (implemented)
- Dataset coverage: `datasets/housing_basics.yaml` (policy memo overview) and `datasets/reduced_e2e_smoke.yaml` (reduced E2E prompts: guardrails, District 9 plan, ledger aggregate, KPI trigger). Scenarios attach the prod-seeded reduced E2E docs: policy `fb400d68-3200-4e07-9231-cea9ee7163eb`, ledger `6806e86f-549f-4588-84de-2dd089a8f7da`, KPI `232d5d61-f083-448f-ae2f-2aa9b9a1a3c0` (content from `tests/data/reduced_e2e/*.md`).
- Harness wiring: Real HTTP calls to the Agent API (`AGENT_BASE_URL`) using HS256 tokens from `AUTH_SHARED_SECRET`; creates conversations via `/v1/conversations`, bulk-attaches documents, then posts `/v1/chat` with `allow_stateless=false`. No stubs; requires `.env.prod`, `EVAL_USER_ID`, and OPENAI credentials.
- Metrics: DeepEval GEval (faithfulness/relevance) + Ragas (context precision/recall) + deterministic citation check. Judge default = GPT-5.1 reasoning-medium for all metrics (OPENAI_API_KEY required).
- Artifacts: JSON under `tests/evals/artifacts/evals/<ts>/<scenario>/result.json` (gitignored) unless `EVAL_ARTIFACTS_DIR` is set.
- Running locally/CI: `cd services/agent-api && uv run pytest tests/evals -m eval` after `source .env.prod` and `export EVAL_USER_ID=11111111-2222-3333-4444-555555555555`. Adds new conversations/attachments in prod; ensure credentials are present.

## Next Steps to Implement
1) Add `services/agent-api/tests/evals` skeleton (core modules, sample YAML scenarios) and gitignore `artifacts/evals/`.
2) Wire FastAPI DI overrides: auth stub, stateless chat flag, read-only DB session, no-op conversation repo, retrieval telemetry sink.
3) Integrate Ragas + DeepEval dependencies via `uv add --dev ragas deepeval` (plus `langsmith[pytest]` if we keep hosted tracking).
4) Build initial scenarios using existing production documents (DocRef list) and run a golden-path pytest to validate harness.
5) Iterate on metric thresholds and judge model defaults; add CI job to run marked `eval` tests on demand (nightly or gated branch label).
