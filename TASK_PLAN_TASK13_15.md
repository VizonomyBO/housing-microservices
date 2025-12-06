# Task Plan – Tasks 13–15 docs/deploy cleanup
_Plan auto-approved per AGENTS.md. Per session constraint, keep plan/tracker files in place after completion._

## Summary
Refresh prod-facing docs and automation so the AWS stack is redeployable with zero manual steps and immediately usable by frontend clients. Confirm converter fail-on-parse behavior (Task 15), update the AWS curl walkthrough + endpoint reference, add an idempotent prod deploy entrypoint, run AWS smoke with new PDFs, and point README to the right runbooks. Work corresponds to `TASK_DEFINITION.md` tasks 13–15 and prompts `task_prompts/13_numerical_sql_enforcement.md`, `task_prompts/14_localstack_verification.md`, `task_prompts/15_cleanup_reset.md`.

## Impacted files (initial)
- `docs/runbooks/prod_setup.md` (AWS curl walkthrough, endpoints, multi-PDF smoke flow)
- `README.md` (entrypoint links)
- `scripts/deploy_ec2_services.sh`, `scripts/provision_remote_stack.sh`, `scripts/use_env.sh` (new idempotent deploy entrypoint/usage notes)
- Potential new helper script for prod deploy
- `prod_sample_run.json`, `scripts/prod_smoke_check.sh` (evidence references)
- `services/agent-api` converter/ingestion Lambdas if fail-on-parse missing
- Tracker docs: `TASK_PLAN_PROGRESS.md`, this plan + tracker

## Risks / Watchouts
- Runbook accuracy must match current AWS endpoints; stale commands could mislead frontend integration.
- Deploy entrypoint must be idempotent and safe to rerun; avoid clobbering existing infra or secrets.
- Fail-on-parse change could break current successful smoke if not already implemented—verify before altering.
- Smoke runs can be slow; ensure unique PDFs to bypass dedupe and capture evidence paths.

## Research (capture sources)
- AWS S3 presigned POST usage and required form fields (source: <https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-UsingHTTPPOST.html>)
- AWS Step Functions `ResultPath` / payload preservation for callbacks and error handling (source: <https://docs.aws.amazon.com/step-functions/latest/dg/input-output-resultpath.html>)

## Ordered Steps (auto-approved)
1. Review current state: prompts 13–15, `TASK_PLAN_PROGRESS.md` rows 13–15, existing runbook/smoke scripts, converter implementation, and endpoint values.
2. Update `docs/runbooks/prod_setup.md` with the latest AWS curl walkthrough (login → presign → S3 POST → poll → attach → chat), multi-PDF smoke steps, and a frontend-oriented endpoint reference (agent/auth/ingest routes/payloads).
3. Add an idempotent prod deploy entrypoint script covering Terraform apply + EC2 service bring-up; document usage alongside existing helpers.
4. Ensure converter fail-on-parse is implemented (Task 15 requirement); adjust code/tests if missing.
5. Refresh `README.md` to point to the runbook and endpoint reference; align any links.
6. Run AWS smoke (`ENV_FILE=.env.active bash scripts/prod_smoke_check.sh` with unique PDFs) and capture evidence/logs; update tracker entries.
7. Leave plan/tracker files in place; stage/commit prod-ready changes when tasks above are done.
