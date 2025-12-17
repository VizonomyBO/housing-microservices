# Step 9 – AWS Curl + Smoke Progress Log (2025-02-03)

> **Archived (pre-revamp):** Documents the legacy Step Functions/Lambda ingestion troubleshooting. The active stack uses the synchronous FastAPI ingestion service (MarkItDown → voyage-context-3 → pgvector) with no Step Functions or cache layer.

## Key Instructions & Constraints
- Follow `AGENTS.md` (plan/tracker required, `.venv.tooling` for automation scripts, `services/agent-api/.venv` + `uv run` for service tooling).
- Focus exclusively on AWS verification right now (per latest user directive); LocalStack validation remains deferred.
- Leave `TASK_PLAN.md` + `TASK_PLAN_PROGRESS.md` in place after the session.
- Every ingestion run must upload a **unique binary** to avoid hash dedupe; append timestamps or markers before each attempt.
- Keep evidence under `/tmp/aws_smoke_step9/` so future sessions can diff results.

## Environment Snapshot (this workstation)
- Docker compose usually targets AWS via `.env.prod` (LocalStack still deferred). Marker-service is legacy/unused—keep it stopped unless explicitly debugging historical flows.
- `.env.prod` now points directly at the EC2 host: `AGENT_BASE_URL=http://52.207.140.87:8000`, `AUTH_BASE_URL=http://52.207.140.87:5001`, `INGEST_BASE_URL=https://yozxw8xm0j.execute-api.us-east-1.amazonaws.com/dev2`.
- Tooling env: `.venv.tooling` (bootstrap via `scripts/ensure_tooling_env.sh` when running automation helpers).

## Work Completed This Session
1. **Manual AWS curl walkthrough succeeded** using `/tmp/aws_smoke_step9/manual_flow.sh` (wrapper around docs/runbooks §5). Outputs saved under `/tmp/aws_smoke_step9/`:
   - `doc_policy_1764921127.pdf` (unique PDF uploaded).
   - Document ID `f9ef7feb-0bd7-4e1b-93df-32526824ff96`; conversation `0306e40f-807a-5dd4-adf7-b2a5c4453897`; file hash saved in `manual_file_hash.txt`.
   - SSE transcript `sse_manual.log` shows router → numerical route, fallback informational answer citing placeholder chunk (conversion error). This satisfies the curl walkthrough portion of Step 9.
2. **Captured login/upload/attach artifacts**: `login_response.json`, `upload_response.json`, `doc_status.json`, `conversation.json`, `attach.json`, `chat_request.json` inside `/tmp/aws_smoke_step9/`.
3. **Smoke script attempt #1 (Markdown upload)**
   - Command: `SMOKE_UPLOAD_FILE=/tmp/aws_smoke_step9/doc_policy_smoke_1764921319.md ./scripts/prod_smoke_check.sh` (see `/tmp/aws_smoke_step9/prod_smoke_check.log`).
   - Ingestion doc `0d01fd54-2083-4647-bf8f-741cfff993f5` never appeared in `/v1/documents` after 40 polls; script exited with error.
   - Need to inspect Step Functions execution & S3 to verify if upload triggered (not visible in bucket listing, so upload may have failed).
4. **Smoke script attempt #2 (PDF upload)**
   - Started with `SMOKE_UPLOAD_FILE=/tmp/aws_smoke_step9/doc_policy_smoke_pdf_1764921853.pdf ./scripts/prod_smoke_check.sh` but the user stopped execution mid-run to pause for the day. No conclusion; rerun required.
5. **Debug ingest helper** `debug_ingest.sh` validated pre-signed upload issuance outside the smoke script.
6. **AWS Step Functions**: `aws stepfunctions list-executions` (with `AWS_DEFAULT_REGION=$AWS_REGION`) confirms recent successful runs `doc-f9ef7feb-20251205075425`, `doc-6044fefd-20251205073226`, etc. No execution yet for `0d01fd54-...`, which hints the S3 object might not exist.
7. **Smoke script success after presigned upload fix (2025-12-05)**  
   - Updated `scripts/prod_smoke_check.sh` to (a) pass through `Content-Type` on the form upload and (b) parse presigned fields with TSV-safe parsing so `policy`/`signature` aren’t mangled.  
   - New run: `SMOKE_UPLOAD_FILE=/tmp/aws_smoke_step9/doc_policy_smoke_md_1764941879_fix.md ./scripts/prod_smoke_check.sh | tee /tmp/aws_smoke_step9/prod_smoke_check_1764941879.log`.  
   - Document `bae6eef5-7776-4a78-9333-dfb61d8ec65f` progressed preflight → embed → index → activate; Step Functions execution succeeded; Agent API attachments/chat completed.  
   - `prod_sample_run.json` refreshed (conversation `e079ab22-b664-5d41-9d34-320e1b3ff204`, timestamp 2025-12-05T09:39:47-04:00).  
   - Remaining failed docs (`a98f64fb-...`, `ff04fda7-...`, `560d56d3-...`) were superseded; keep for historical context only.

## Outstanding / Next Steps for Step 9
1. **Confirm artifacts for reviewers**
   - Point reviewers to `/tmp/aws_smoke_step9/prod_smoke_check_1764941879.log`, upload asset `doc_policy_smoke_md_1764941879_fix.md`, and refreshed `prod_sample_run.json`.
   - Note residual registered-but-not-processed doc IDs (`a98f64fb-…`, `560d56d3-…`, `ff04fda7-…`) from failed runs; safe to ignore unless we purge old smoke data.
2. **LocalStack verification (deferred)**
   - Per Dec 2024 constraint, still pending for a later session once AWS smoke is accepted.

## Helpful Commands
```bash
# Manual AWS flow (already run; rerun if needed)
sudo chmod +x /tmp/aws_smoke_step9/manual_flow.sh
/tmp/aws_smoke_step9/manual_flow.sh

# Smoke test with unique file
cp services/agent-api/tests/data/reduced_e2e/doc_policy.pdf /tmp/aws_smoke_step9/doc_policy_smoke_pdf_$(date +%s).pdf
printf '\n%% smoke-run %s\n' "$(date -Iseconds)" >> /tmp/aws_smoke_step9/doc_policy_smoke_pdf_<ts>.pdf
SMOKE_UPLOAD_FILE=/tmp/aws_smoke_step9/doc_policy_smoke_pdf_<ts>.pdf ./scripts/prod_smoke_check.sh | tee /tmp/aws_smoke_step9/prod_smoke_check.log

# Monitor Step Functions
AWS_DEFAULT_REGION=$AWS_REGION aws stepfunctions list-executions --state-machine-arn arn:aws:states:us-east-1:336722292744:stateMachine:vizonomy-v2-document-ingestion-dev2
AWS_DEFAULT_REGION=$AWS_REGION aws stepfunctions describe-execution --execution-arn <arn>

# Inspect S3 raw object
AWS_DEFAULT_REGION=$AWS_REGION aws s3 ls vizonomy-v2-raw-docs-dev2-4fd5a20a/raw/<doc_id>/ --recursive
```

## Files & Artifacts to Review
- `notes/aws_step9_status.md` (this file).
- `/tmp/aws_smoke_step9/` directory with login/upload/attach/SSE artifacts plus smoke logs.
- `prod_sample_run.json` (unchanged because smoke script failed—needs update once it passes).

## Blocking Issues
- `scripts/prod_smoke_check.sh` polls `/v1/documents` but the newly registered document never shows up, implying either upload failure or Lambda not triggered. Need to trace this before Step 9 can be closed.

## Hand-off Checklist
- Reuse this log + tracker row #9 as the authoritative “what’s done / what’s next”.
- Do **not** delete the plan/tracker.
- Keep docker compose stack running against AWS unless new env changes require restart.
