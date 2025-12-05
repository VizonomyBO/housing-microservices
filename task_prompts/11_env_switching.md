# Task 11 – Automate env switching (fresh session prompt)

## Objective
Create a single source of truth to toggle between AWS and LocalStack (or future local emulation) for compose, scripts, and lambdas. It’s allowed to touch any `.env*` files (gitignored) and to add helper scripts/templates.

## Context (carry-over)
- AWS mode is working (INGEST_BASE_URL=https://gs6w1i52n4.execute-api.us-east-1.amazonaws.com/dev2, Postgres 44.216.103.232). LocalStack is deferred for now, but plan for it later. 
- Auth/user services should already point at AWS Postgres after Task 10.
- Real PDF for ingestion: `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf`.
- Tracker Step 9 complete; next tasks depend on consistent env toggling.

## Requirements
- Provide a simple toggle (script or env template) that sets all relevant vars: DB URLs, service base URLs, INGEST_BASE_URL, USE_LOCALSTACK, AWS creds, etc.
- Ensure compose, smoke scripts (`scripts/prod_smoke_check.sh`), terraform helpers, and runbooks can consume the toggle without manual edits.
- Document how to switch (one or two commands).
- If this changes defaults, update subsequent prompt files.

## Suggested steps
1) Inspect current env usage in compose overrides, scripts (`scripts/prod_smoke_check.sh`, terraform wrappers, runbooks).  
2) Add a switch script (e.g., `scripts/use_env.sh aws|local`) or env templates (`.env.aws.template`, `.env.local.template`) plus docs.  
3) Verify both modes at least partially: for AWS, a quick login curl; for LocalStack, just ensure vars resolve (full LocalStack run is Task 13).  
4) Update docs/runbooks with the new switching instructions; update `TASK_PLAN_PROGRESS.md` row 11.

## Deliverables
- Working toggle mechanism with clear instructions.
- Minimal verification notes (e.g., login curl in AWS mode).

## Hand-off
- Note any new env var names/paths in `task_prompts/12_ec2_services.md` if they impact deployment.
