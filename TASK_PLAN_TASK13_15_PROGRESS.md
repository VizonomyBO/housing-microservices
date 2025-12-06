# Task Plan Progress – Tasks 13–15 docs/deploy cleanup
_Tracker for TASK_PLAN_TASK13_15.md (plan auto-approved). Leave in place per session constraints._

- [x] Step 1: Review current state (prompts 13–15, tracker rows, runbook/scripts, converter).
- [x] Step 2: Update docs/runbooks with AWS curl walkthrough + frontend endpoint reference.
- [x] Step 3: Add idempotent prod deploy entrypoint script and usage notes.
- [x] Step 4: Verify/enforce converter fail-on-parse behavior.
- [x] Step 5: Refresh README links to runbook/endpoint reference.
- [x] Step 6: Run AWS smoke with unique PDFs, capture evidence, update tracker.
- [ ] Step 7: Prepare commit/staging (prod-ready), leave plan/tracker files.

Notes / evidence:
- Commands/logs: `ENV_FILE=.env.active bash scripts/prod_smoke_check.sh |& tee /tmp/prod_smoke_latest.log`
- Document IDs / hashes: policy `32b1ad98-309d-4cac-b5b4-2164bdc27989`, ledger `a7a58498-1ae4-47d6-a2dd-3152a5327519`, KPI `9c1954d8-4178-46c2-a5bf-0cd9de83d5e8` (stamped copies to avoid dedupe)
- Smoke evidence path: `/tmp/prod_smoke_latest.log`, `prod_sample_run.json` (AWS mode)
