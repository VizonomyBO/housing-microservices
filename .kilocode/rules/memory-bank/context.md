# Context

## Current Focus
The project is currently focused on verifying the AWS deployment and ensuring the ingestion service is functioning correctly after recent architectural changes.

### Active Tasks
-   **AWS Verification (Step 9)**: Rerun the AWS curl walkthrough and `scripts/prod_smoke_check.sh` against the real stack.
-   **Ingestion Service**: Verify the new FastAPI-based ingestion service (replacing Lambda) on EC2.
-   **Smoke Tests**: Ensure each upload is unique to avoid deduplication short-circuits, capture command evidence/IDs.

## Recent Changes
-   **Ingestion Architecture**: Replaced Lambda-based ingestion with a dedicated FastAPI `ingestion-service` running on EC2.
-   **Shared Data Layer**: Consolidated database models and repositories into `packages/shared_data_layer`.
-   **Tooling**: Standardized on `uv` for dependency management and environment setup.
-   **Testing Docs**: Updated `docs/testing/llm_eval_quality_improvements.md` with HyDE + numeric rerank guidance, structured outputs with citations, and a pytest runbook for evals.
-   **Agent Eval Hardening**: Agent answer composer now performs HyDE-style rewrites + numeric-aware reranking of attachment chunks, builds structured prompts with per-fact [c#] citations, and appends citation footnotes; eval thresholds in `tests/evals/datasets/reduced_e2e_smoke.yaml` raised to 0.5 faithfulness/relevance and 0.8 citation coverage. Attachment previews widened (8 chunks/2400 chars).
-   **No eval shortcuts**: AGENTS.md and task docs now require using real retrieval (vector + BM25/FTS where available) instead of preview-only heuristics, and citation validation must align to actual retrieved chunks.

## Next Steps
1.  Run `scripts/prod_smoke_check.sh` in AWS mode.
2.  Verify document upload and processing via the new ingestion service.
3.  Update tracker files (`TASK_PLAN.md`, `TASK_PLAN_PROGRESS.md`) with results.
4.  (Future) Re-verify LocalStack setup.

## Known Issues / Constraints
-   **LocalStack**: Setup is currently broken or deferred; focus is on AWS verification.
-   **Swagger Service**: Currently not deployed/available in the active profile.
-   **Database**: Remote Postgres host must expose two logical databases (`housing` and `auth_db`).
