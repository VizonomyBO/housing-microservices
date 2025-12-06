# Task 16 – Cleanup, quality gates, and data reset for final deploy (fresh session prompt)

## Objective
Finish with a clean codebase and fresh data: run quality gates, tidy docs, and reset documents/chats in the DBs so the final deploy starts with no old smoke artifacts.

## Context (carry-over)
- AWS smoke is passing on the rebuilt stack via the new FastAPI ingestion service on EC2 (Task 14 done). Latest run used three stamped PDFs; doc IDs: `2dc9b58f-217a-48a3-945c-8edae96c73c5`, `776f45dc-11e2-4b4a-b6b0-2c75bc39066c`, `bfbeb618-d493-47ef-a70a-f3d35d567277` (log `/tmp/prod_smoke_fastapi.log`).
- Env switching and EC2 deployment are done. LocalStack verification may be done or documented.
- Plan/tracker/AGENTS can be updated as needed; `.env*` files are gitignored and can be adjusted.
- Marker-service is legacy; keep it stopped unless a task explicitly calls for it.

## Requirements
- Run quality gates: `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto` (or scope appropriately if constraints).
- Clean up ingestion/chat data in the DBs (both `housing` and `auth_db` as appropriate): remove smoke documents, conversations, and related artifacts so final deploy is fresh. Document exact SQL/commands used.
- Update docs/runbooks with final run commands; ensure `TASK_PLAN_PROGRESS.md` reflects completion.
- Converter fail-on-parse is already in place (Task 15 directive satisfied); ensure deployed images match repo state and note any remaining cleanup for Lambda/Gateway if still referenced in docs.
- If plan/tracker files should be removed per AGENTS, do so unless told otherwise; otherwise leave them with “completed” notes.
- Swagger remains unhealthy; safe to ignore for backend/frontend readiness as long as core services (agent-api/auth/user/ingestion-service) are reachable.

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
