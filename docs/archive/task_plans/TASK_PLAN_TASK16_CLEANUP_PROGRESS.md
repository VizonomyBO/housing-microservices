# Task 16 Tracker – Cleanup, Quality Gates, Data Reset
_Tracks TASK_PLAN_TASK16_CLEANUP.md; keep in repo after completion per session constraint._

- [x] Step 1: Confirm env/DB targets (AWS) and backup needs.
- [x] Step 2: Delete smoke artifacts from housing/auth_db with documented SQL + counts.
- [x] Step 3: Run quality gates (`uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`), fix issues.
- [x] Step 4: Update trackers/runbooks with commands/evidence; sync `TASK_PLAN_PROGRESS.md` row 16.
- [x] Step 5: Sanity check login/health after cleanup; note residual risks/TODOs.

Notes / Evidence:
- Housing DB reset (AWS):
  - Pre-clean counts: documents=27, conversations=4, messages=0, chunks=21.
  - Commands: `psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -c "begin; delete from conversations; delete from documents; commit;"`
  - Post-clean counts: documents=0, conversations=0, messages=0, chunks=0, artifacts/ingestion_jobs/uploaded_files/conversation_documents=0.
- Auth DB cleanup: `psql ... -d $AUTH_DB -c "begin; delete from refresh_tokens; commit;"` → users=1 (demo), refresh_tokens=0.
- Quality gates (services/agent-api): `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto` → all passed (pytest: 168 passed, deprecation warnings from testcontainers wait decorators).
- Runbooks/trackers updated: `docs/runbooks/prod_setup.md` now documents data reset + quality gate commands; `TASK_PLAN_PROGRESS.md` row 16 marked complete.
- Sanity checks: `curl` health for auth/agent returned 200; login against `$AUTH_BASE_URL/v1/auth/login` with demo creds returned 200 and emitted an access token (length 293).
