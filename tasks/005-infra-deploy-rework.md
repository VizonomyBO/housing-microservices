# [Completed] Task: Rework Infra & Deployment for Cache-Free Stack

Follow `.kilocode/rules/memory-bank-instructions.md` and `AGENTS.md`; create/update a plan + tracker in the repo root.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Align infrastructure and deployment automation with the simplified services (auth, user, ingestion, agent, Postgres), removing Lambda/Step Functions/Valkey/telemetry remnants and adding the new deploy script modes.

## Scope
- Update `ArchaaS` Terraform (or equivalent infra configs) to drop Step Functions/Lambda ingestion artifacts, cache/rate-limit infra, and reduced-scope/telemetry extras; retain EC2 + Postgres + S3/LocalStack as needed for the new pipeline.
- Ensure docker-compose.ec2.yml (or successor) matches the simplified stack and cleans up any legacy containers/config on deploy.
- Implement a new deployment automation script with modes: (a) full infra/app redeploy (terraform down/up, rebuild/redeploy services; protect with confirmation and avoid DB teardown/backups), (b) service-only image rebuild/push/update, and (c) hot patch (ssh + container patch + restart). Remove or deprecate conflicting old scripts/runbooks.
- Update runbooks/docs to reflect the new deployment flow and safety gates.

## Deliverables
- Infra configs free of Lambda/Step Functions/Valkey/telemetry for the ingestion/chat path, matching the target services.
- New deployment automation script with the required modes and documented usage; old scripts cleaned up or clearly deprecated.
- Updated EC2 compose/profile reflecting the simplified services.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`
