# Task 14 – Cleanup, quality gates, and data reset for final deploy (fresh session prompt)

## Objective
Finish with a clean codebase and fresh data: run quality gates, tidy docs, and reset documents/chats in the DBs so the final deploy starts with no old smoke artifacts.

## Context (carry-over)
- AWS smoke is passing (doc `bae6eef5-7776-4a78-9333-dfb61d8ec65f`, convo `e079ab22-b664-5d41-9d34-320e1b3ff204`). Real PDF: `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf`.
- Env switching and EC2 deployment should be done. LocalStack verification may be done or documented.
- Plan/tracker/AGENTS can be updated as needed; `.env*` files are gitignored and can be adjusted.

## Requirements
- Run quality gates: `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto` (or scope appropriately if constraints).
- Clean up ingestion/chat data in the DBs (both `housing` and `auth_db` as appropriate): remove smoke documents, conversations, and related artifacts so final deploy is fresh. Document exact SQL/commands used.
- Update docs/runbooks with final run commands; ensure `TASK_PLAN_PROGRESS.md` reflects completion.
- If plan/tracker files should be removed per AGENTS, do so unless told otherwise; otherwise leave them with “completed” notes.

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
