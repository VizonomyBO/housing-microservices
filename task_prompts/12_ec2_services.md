# Task 12 – Deploy services to EC2 (same host as Postgres) (fresh session prompt)

## Objective
Package and run agent-api, auth-service, and user-service on the existing EC2 that hosts Postgres (marker-service is legacy and should be ignored unless explicitly requested). Services must use public IP/hostnames for DB and peers so they can later be moved off-box without code changes. Expose required ports via security groups. Automate start/stop/update.

## Context (carry-over)
- AWS infra already deployed (Postgres at 52.207.140.87:5432, API Gateway https://yozxw8xm0j.execute-api.us-east-1.amazonaws.com/dev2). Auth/user should be AWS-ready after Task 10.
- Env selection uses `scripts/use_env.sh <prod|dev|local>` which returns the chosen env file; source it and pass `--env-file` to compose/deploy. `.env*` edits are allowed; they’re gitignored.
- Real ingestion file: `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf` (current converter emits a placeholder; use a freshly generated PDF like `/tmp/ec2_policy_generated.pdf` for smoke runs). Smoke script is working in AWS.
- LocalStack verification is deferred to the next task.

## Requirements
- Provide automation (bash/systemd/unit templates or a deploy script) to push and run the four services on the EC2 host:
  - Use public endpoints/hosts in env vars (DB host/IP, service URLs).
  - Expose ports (agent-api 8000, auth 5001, user 5002, swagger 3000 if needed). Marker-service is legacy/unused—exclude it unless explicitly testing old flows.
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

## Automation helper (updated)
- Use `scripts/deploy_ec2_services.sh` to push the repo to the EC2 host (default `/opt/housing-microservices`), install Docker/Compose if missing, generate a public-host env, and run `docker-compose.ec2.yml` for `agent-api`, `auth-service`, `user-service` (optional `--include-swagger`). Marker-service is skipped by default; use `--include-marker` only if explicitly testing that legacy path.
- Example: `env_file=$(scripts/use_env.sh prod) && ENV_FILE="$env_file" scripts/deploy_ec2_services.sh --host 52.207.140.87 --open-ports` (defaults to the terraform SSH key). `--action stop` tears the stack down; `--no-sync`/`--no-build` speed up restarts.
- The helper can update the EC2 security group for ports 8000/5001/5002/3000 when `--open-ports` is provided (requires AWS creds in the env file). Health checks and login curls are echoed after deployment.

## Deliverables
- Automation script(s) + any unit files/config to start/stop/update the services on EC2.
- Verification notes (commands + outcomes).

## Hand-off
- If env names or ports change, propagate to `task_prompts/15_localstack_verification.md` and `task_prompts/16_cleanup_reset.md`.
- Once the task is finished, commit all files added/edited by this thread.
