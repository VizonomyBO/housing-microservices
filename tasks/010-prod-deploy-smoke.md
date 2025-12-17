# Task: Production Deploy + Smoke Script (Completed)

Follow `.kilocode/rules/memory-bank-instructions.md` and `AGENTS.md`; create/update a plan + tracker in the repo root. Use service-specific AGENTS when touching those packages. The agent must commit the changes before terminating the task. Once the task is done, mark this as completed in the title.

## Objective
- Create a deployment script that provisions/updates the ingestion-first stack on prod (agent-api, ingestion-service, auth-service, user-service, Postgres) with correct ports/envs, deploy this new system and then run the full smoke (ingestion upload → poll → attach → chat) end-to-end with the document at `services/agent-api/evals/data/MEX_2016_Mexico Financial Sector Assessment Program Housing Finance.pdf`. Iterate until every component runs correctly; execute the smoke flow when ready.

## Scope
- Script should handle env sourcing, remote sync/build/restart (compose on EC2), and health checks for all services. Align with `scripts/deploy_stack.sh` patterns or supersede them if needed.
- Run the prod smoke using the FastAPI ingestion path (MarkItDown → voyage-context-3 embeddings) and capture results. Ensure ports/CORS/creds are correctly wired.
- If smoke responses are empty/invalid, fix the deploy configuration or agent/ingestion settings until the prod flow is coherent.

## Deliverables
- Deployment script + brief usage notes covering options (host, env file, build/sync toggles).
- Successful prod smoke run (logs/artifacts) proving upload → activation → attachment → chat works end-to-end.

## References
- `docs/runbooks/prod_setup.md`, `scripts/deploy_stack.sh`, `scripts/prod_smoke_check.sh`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`
