# Task 16 Plan – Cleanup, Quality Gates, Data Reset
_Plan auto-approved per AGENTS.md. Per session constraints, keep this plan/tracker after completion for continuity._

## Summary
Finalize Task 16 by running all Python quality gates, cleaning smoke/test artifacts from the AWS databases (housing + auth_db as applicable), and updating runbooks/tracker with the final commands/evidence so the next deploy starts fresh.

## Impacted files / assets
- Tracker/docs: `TASK_PLAN_TASK16_CLEANUP_PROGRESS.md`, `TASK_PLAN_PROGRESS.md`, relevant runbooks under `docs/runbooks/`
- Potential helper notes: `notes/` entries for cleanup evidence, `.env*` (gitignored) for DB connection sourcing
- No code changes expected unless formatting/linting fixes arise from quality gates

## Risks / Watchouts
- Deleting the wrong records could remove demo/base data; double-check IDs and limit deletes to smoke artifacts.
- Quality gates may modify files (ruff format/fix); keep track of auto-fixes for final commit.
- pytest may be slow; may need to scope if failures are unrelated—document any deviations.

## Research / Sources
- Internal schemas (`packages/shared_data_layer`) for cascade behavior on documents/conversations. No external sources required so far.

## Ordered Steps (auto-approved)
1. Validate env/DB targets: confirm `.env.active` (or `.env.prod.aws`) points to AWS housing/auth_db; note any backups needed.
2. Identify smoke artifacts (docs/conversations/users) from recent runs and delete them in housing/auth_db with targeted SQL; record commands and counts.
3. Run quality gates via uv: `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto` (scope only if necessary) and address any failures.
4. Update tracker/runbooks: mark `TASK_PLAN_TASK16_CLEANUP_PROGRESS.md` + `TASK_PLAN_PROGRESS.md` row 16, add cleanup commands/evidence and any doc/runbook tweaks.
5. Sanity check services post-cleanup (login + health endpoints) and capture final notes/risks for hand-off.

## Notes
- Plan is auto-approved; proceed immediately. Keep plan/tracker files in repo after completion per current session guidance.
