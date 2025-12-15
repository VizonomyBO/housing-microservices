# Task 15 – LocalStack (or docker-based) verification (fresh session prompt)

## Objective
Run the full ingestion + chat flow locally without AWS. LocalStack Pro is unavailable for Step Functions/Lambda, so prefer a docker-based emulation or the best available LocalStack setup. This runs after AWS + EC2 deployment is stable.

## Context (carry-over)
- AWS path is proven. Env switching should exist (Task 11). Services may also be deployable on EC2 (Task 12).
- Task 14 is complete: ingestion now flows through the FastAPI service on EC2 (`INGEST_BASE_URL` defaults to http://52.207.140.87:8085); Lambda/S3/Gateway are bypassed for prod.
- Real ingestion file: `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf` (note: current AWS stack converts it to a placeholder; consider using a fresh generated PDF like `/tmp/ec2_policy_generated.pdf`).
- Many repo files are dirty; do not revert unrelated changes.
- Marker-service is legacy; keep it off unless a task explicitly asks to run it.

## Requirements
- Stand up a local stack that exercises upload → ingest → chat without mocks, mirroring the new FastAPI ingestion flow (or document if Lambda emulation is still required).
- If LocalStack can’t run Step Functions/Lambda nor EC2 due to pro features, document the workaround (docker-compose emu, or use the FastAPI ingestion service locally) and note gaps.
- Run `scripts/prod_smoke_check.sh` (or a local variant) pointing at local endpoints; record pass/fail and gaps.
- Update tracker row 15 and docs/runbooks with the local recipe.
- `.env*` files may be edited; ensure switching script covers this mode.

## Suggested steps
1) Wire env switching to a “local” profile (LocalStack or docker emu).  
2) Bring up local infra (terraform to LocalStack if possible, or compose-based lambdas/Step Functions emulator).  
3) Run curl/presigned upload + poll + attach + chat; note any missing features due to LocalStack limitations.  
4) Capture evidence/logs; update runbooks and tracker.  
5) If infeasible, clearly document blockers and proposed alternatives.

## Deliverables
- A reproducible local flow (or documented blockers) with commands/evidence.
- Updated tracker and runbook notes for local mode.

## Hand-off
- Record any remaining cleanup or schema reset needs for the final task in `task_prompts/14_cleanup_reset.md`.
- Once the task is finished, commit all files added/edited by this thread.
