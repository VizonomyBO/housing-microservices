# Task 12 – Deploy services to EC2 (same host as Postgres) (fresh session prompt)

## Objective
Package and run agent-api, auth-service, user-service, and marker-service on the existing EC2 that hosts Postgres. Services must use public IP/hostnames for DB and peers so they can later be moved off-box without code changes. Expose required ports via security groups. Automate start/stop/update.

## Context (carry-over)
- AWS infra already deployed (Postgres at 44.216.103.232:5432, API Gateway https://gs6w1i52n4.execute-api.us-east-1.amazonaws.com/dev2). Auth/user should be AWS-ready after Task 10.
- Env switching script/template should exist after Task 11 (feel free to reuse/extend). `.env*` edits are allowed; they’re gitignored.
- Real ingestion file: `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf`. Smoke script is working in AWS.
- LocalStack verification is deferred to the next task.

## Requirements
- Provide automation (bash/systemd/unit templates or a deploy script) to push and run the four services on the EC2 host:
  - Use public endpoints/hosts in env vars (DB host/IP, service URLs). 
  - Expose ports (agent-api 8000, auth 5001, user 5002, marker 8004, swagger 3000 if needed).
  - Ensure dependencies (Python env, uv/docker) are installed or containerize the services for the EC2.
- Keep DB+services decoupled; future relocation should only require env changes, not code.
- Update security groups/iptables if necessary.
- Record commands/evidence; update tracker row 12.

## Suggested steps
1) Decide packaging: docker-compose on EC2 vs. systemd+uv. Prefer reproducible, scriptable approach.  
2) Author a deploy script (e.g., `scripts/deploy_ec2_services.sh`) that: syncs env, pulls/builds images or venvs, runs containers/services, and opens ports.  
3) Verify on EC2: health endpoints for each service, a login curl to auth, and an agent-api `/health`.  
4) Document run/stop/update commands; note any SG changes.  
5) Update `TASK_PLAN_PROGRESS.md` row 12 and, if needed, next prompt.

## Deliverables
- Automation script(s) + any unit files/config to start/stop/update the services on EC2.
- Verification notes (commands + outcomes).

## Hand-off
- If env names or ports change, propagate to `task_prompts/13_localstack_verification.md` and `task_prompts/14_cleanup_reset.md`.
