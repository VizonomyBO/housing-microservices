# LLM Agent Eval Suite Proposal

## Goals & Constraints
- Type-safe, OOP-first eval scenarios runnable via `uv run pytest`, not bespoke CLIs.
- Exercise the real Agent API over HTTP using production credentials (`.env.prod`); no dependency overrides, stubs, or mocks.
- Target the ingestion-first, text-only stack (FastAPI ingestion, BM25 + pgvector with Voyage `voyage-context-3` + `rerank-2.5`, ReAct agent with Pyodide tool). Avoid graph/planner/cache/reduced-scope paths.
- Attach existing prod documents stored in AWS Postgres/S3, load conversation history, and evaluate responses with LLM-as-judge metrics.
- Capture retrieval traces (chunk IDs, scores, latency) for metrics and write eval artifacts to JSON under `artifacts/evals/` (gitignored).
- Treat eval runs as read-only at the product level: create real conversations/attachments but avoid custom in-memory stores or bypassed persistence layers.
- Enable a focused metric stack (faithfulness, answer/context relevance, latency, grounding) with a single default judge model (`gpt-5.1`) and an env override. Set `reasoning.effort` to `medium` via API parameters rather than encoding it in the model name.

## Recommended Stack (grounded in research)
- **DeepEval** for pytest-friendly LLM-as-judge metrics and typed test cases (30+ metrics, supports component/e2e eval) [deepeval docs](https://deepeval.com/docs/getting-started).
- **Ragas** for retrieval-oriented metrics (faithfulness, answer relevancy, context precision/recall) with pytest CI mode [ragas pytest guide](https://docs.ragas.io/en/v0.3.0/howtos/applications/add_to_ci/).
- **TruLens RAG triad** (context relevance, groundedness, answer relevance) as a conceptual baseline for custom metrics [trulens RAG triad](https://www.trulens.org/getting_started/core_concepts/rag_triad/).
- **Judge models**: Default to **gpt-5.1** for gating, and set `reasoning.effort` (`low`|`medium`|`high`) in the request body; allow overrides via `EVAL_JUDGE_MODEL` but keep the surface limited to OpenAI judges to avoid drift.

## Proposed Architecture & Abstractions
- **Type-safe scenario models (Pydantic v2)**:
  - `DocRef`: `{doc_id: UUID, version_id: str | None, title: str}` representing existing DB/S3 documents to attach.
  - `Turn`: `{role: Literal["user","assistant"], content: str, attachments: list[DocRef] | None}` for multi-turn histories.
  - `Expectation`: `{label: str, rubric: str, expected_answer: str | None, citations_required: bool}`.
  - `MetricSpec`: enum of built-in metrics (`faithfulness`, `context_precision`, `answer_relevancy`, `toxicity`, `latency`, etc.) with optional thresholds and judge model.
  - `EvalScenario`: name, description, tenant/scope, dataset tag, `turns`, `expectations`, `metric_specs`, optional seeds for reproducibility.
  - `EvalRunConfig`: judge model defaults, OpenAI/Anthropic keys, `stateless=True`, `capture_retrieval=True`, `read_only_db=True`, output path.
- **Execution harness (pytest + httpx)**:
  - Call the live Agent API (`AGENT_BASE_URL`) with HS256 tokens minted from `AUTH_SHARED_SECRET`; no DI overrides or auth stubs.
  - Create conversations via `/v1/conversations`, bulk-attach existing documents, and post `/v1/chat` with `allow_stateless=false`.
  - Capture retrieval data (chunk IDs/scores/latency) via response telemetry and feed them to metrics; write artifacts locally.
- **Metric layer**:
  - Ragas metrics for retrieval quality: context precision/recall, answer relevance, faithfulness using retrieved chunks vs. answer.
  - DeepEval metrics for factuality/hallucination, toxicity, coherence, and custom GEval rubrics per `Expectation`.
  - Custom deterministic metrics: latency budgets, citation coverage (% of sentences with citations), empty-context guard.
  - Support per-scenario thresholds and judge model overrides; default to `gpt-5.1` for gating with an env override when needed.
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
 1) Mints an HS256 token, creates a conversation via `/v1/conversations`, and bulk-attaches documents.
 2) Builds conversation history + attachments from `Scenario` and calls `/v1/chat` (live API).
 3) Captures retrieval traces via `EvalTelemetrySink`.
 4) Evaluates metrics (Ragas/DeepEval/custom) and returns a typed `EvalResult`.

## Data Safety (read prod, do not write)
- Use production credentials and real endpoints; no stubs or mocking. Expect real conversations/attachments to be created during evals.
- Avoid re-uploading docs; reference existing `doc_id`/`version_id` via `DocRef` so the harness stays read-mostly.
- Keep eval-side artifacts and judge transcripts on disk only (`artifacts/evals/`, gitignored); do not push judge content into the app DB.

## Metrics & Judges
- **Retrieval**: context precision/recall, answer relevance, groundedness (TruLens triad), chunk coverage (% of cited chunks).
- **Response quality**: faithfulness/hallucination (GEval/DeepEval), fluency/coherence, safety/toxicity.
- **Operational**: latency budgets per scenario, token/price accounting, fallback/dedupe detection.
- **Judges**: default `gpt-5.1` with `reasoning.effort=medium` (env override supported); keep the judge surface limited to OpenAI for consistency and cache calls locally to stabilize runs.

## Execution Commands (proposed)
- Local dev: `cd services/agent-api && uv run pytest tests/evals -m eval --maxfail=1`
- Record artifacts only: `EVAL_ARTIFACTS_DIR=artifacts/evals/$(date +%s) uv run pytest tests/evals -m eval --disable-warnings -q`

## Current Eval Suite (implemented)
- Dataset coverage: `datasets/housing_basics.yaml` (policy memo overview) and `datasets/reduced_e2e_smoke.yaml` (reduced E2E prompts: guardrails, District 9 plan, ledger aggregate, KPI trigger). Scenarios attach the prod-seeded reduced E2E docs: policy `fb400d68-3200-4e07-9231-cea9ee7163eb`, ledger `6806e86f-549f-4588-84de-2dd089a8f7da`, KPI `232d5d61-f083-448f-ae2f-2aa9b9a1a3c0` (content from `tests/data/reduced_e2e/*.md`).
- Harness wiring: Real HTTP calls to the Agent API (`AGENT_BASE_URL`) using HS256 tokens from `AUTH_SHARED_SECRET`; creates conversations via `/v1/conversations`, bulk-attaches documents, then posts `/v1/chat` with `allow_stateless=false`. No stubs; requires `.env.prod`, `EVAL_USER_ID`, and OPENAI credentials.
- Metrics: DeepEval GEval (faithfulness/relevance) + Ragas (context precision/recall) + deterministic citation check. Judge default = `gpt-5.1` with `reasoning.effort=medium` for all metrics (override via `EVAL_JUDGE_MODEL`); other judge models are intentionally not wired.
- Artifacts: JSON under `tests/evals/artifacts/evals/<ts>/<scenario>/result.json` (gitignored) unless `EVAL_ARTIFACTS_DIR` is set.
- Running locally/CI: `cd services/agent-api && uv run pytest tests/evals -m eval` after `source .env.prod` and `export EVAL_USER_ID=11111111-2222-3333-4444-555555555555`. Adds new conversations/attachments in prod; ensure credentials are present.

## Next Steps to Implement
1) Keep `services/agent-api/tests/evals` skeleton (core modules, YAML scenarios) current and gitignore `artifacts/evals/`.
2) Ensure the runner always hits the live Agent API with minted HS256 tokens and existing doc IDs (no auth/DI stubs).
3) Keep DeepEval/Ragas dependencies in sync via `uv`.
4) Maintain scenarios using existing production documents (DocRef list) and run a golden-path pytest to validate harness.
5) Iterate on metric thresholds and judge model defaults; add CI job to run marked `eval` tests on demand (nightly or gated branch label).
