# Task 15 – Cleanup, quality gates, and data reset for final deploy (fresh session prompt)

## Objective
Finish with a clean codebase and fresh data: run quality gates, tidy docs, and reset documents/chats in the DBs so the final deploy starts with no old smoke artifacts.

## Context (carry-over)
- AWS smoke is passing on the rebuilt stack (doc `595ba20f-f115-4538-99e0-db67f676b7c1`, convo `7370d175-4b0f-51db-bc75-4b852e4ada9e`). Latest upload used `/tmp/ec2_policy_generated.pdf` to avoid the marker converter placeholder on the repo PDF.
- Env switching and EC2 deployment should be done. LocalStack verification may be done or documented.
- Plan/tracker/AGENTS can be updated as needed; `.env*` files are gitignored and can be adjusted.
- Marker-service is legacy; keep it stopped unless a task explicitly calls for it.

## Requirements
- Run quality gates: `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto` (or scope appropriately if constraints).
- Clean up ingestion/chat data in the DBs (both `housing` and `auth_db` as appropriate): remove smoke documents, conversations, and related artifacts so final deploy is fresh. Document exact SQL/commands used.
- Update docs/runbooks with final run commands; ensure `TASK_PLAN_PROGRESS.md` reflects completion.
- Flip the converter behavior so failed parses stop the pipeline: treat conversion errors as fatal, let Step Functions mark the ingestion as `failed`, and surface the failure reason via finalizer so API/UI block attaching failed docs. Remove placeholder-content fallback for converter errors.
- If plan/tracker files should be removed per AGENTS, do so unless told otherwise; otherwise leave them with “completed” notes.
- Swagger remains unhealthy; safe to ignore for backend/frontend readiness as long as core services (agent-api/auth/user) are reachable.

## Suggested steps
1) Ensure env points to the target DBs (AWS) before deletion; back up if needed.  
2) Execute cleanup SQL/scripts to remove smoke docs/chats/users as agreed; record commands.  
3) Run quality gates; capture any failures and fixes.  
4) Update tracker row 14 and any lingering runbook edits; summarize final state.  
5) Final sanity check: quick login + health endpoint to confirm services remain up after cleanup.

## Deliverables
- Evidence of cleanup (commands, counts) and passing quality gates (or documented exceptions).
- Updated tracker/runbooks; optional removal of plan/tracker files if policy allows.

## Hand-off
- Note any remaining risks or TODOs for final deploy in plan/AGENTS if applicable.
- Once the task is finished, commit all files added/edited by this thread.
