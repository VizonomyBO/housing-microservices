# Task 10 – Harden AWS-mode compose for auth/user (fresh session prompt)

## Objective
Run auth-service and user-service locally against the AWS Postgres host so JWT login works without manual tokens when the stack points at AWS. Ensure `.env*` files reflect the remote DB and any required hostnames/ports.

## Current state (context to avoid re-discovery)
- AWS stack live: API Gateway `https://gs6w1i52n4.execute-api.us-east-1.amazonaws.com/dev2`; raw bucket `vizonomy-v2-raw-docs-dev2-4fd5a20a`; processed bucket `vizonomy-v2-processed-artifacts-dev2-4fd5a20a`; Postgres on EC2 `44.216.103.232:5432` (`housing`, `auth_db`, user/pass `vizonomy_user`/`iSQOjvXTBzJBcGCCt4koPDno`).
- Compose already points agent-api at AWS via `.env.prod.aws` with `USE_LOCALSTACK=0`.
- AWS smoke is passing; tracker Step 9 is done. Real PDF lives at `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf`.
- Many files are dirty in git; do not revert unrelated work.

## Requirements
- Update compose/override/env so auth-service and user-service use the remote Postgres when `USE_LOCALSTACK=0`.
- Health-check auth endpoints (`/v1/auth/login`, `/v1/health`) with AWS DB to confirm JWT issuance.
- Keep `.env*` updates in repo if needed (gitignored is fine); it’s allowed to edit `.env.prod.aws` and friends.
- If changes affect later tasks, append a short note to the next prompt files in `task_prompts/`.

## Suggested steps
1) Read `docker-compose.prod.override.yml` and `.env.prod.aws`; align `AUTH_DATABASE_URL`/`POSTGRES_HOST` for auth/user services to the AWS Postgres host.  
2) Restart only auth-service/user-service in AWS mode.  
3) Run login curl using demo creds (`demo.client@example.com` / `ChangeMe!123`) to verify token issuance.  
4) Update docs/runbooks if commands change; update tracker `TASK_PLAN_PROGRESS.md` row 10.  
5) If you add env vars, propagate to any helper scripts that source `.env.prod.aws`.

## Deliverables
- Auth/user services working against AWS DB in compose AWS mode.
- Notes in tracker row 10 and, if needed, short deltas in the next task prompt. Evidence: curl/login output or log snippet.

## Hand-off
- If anything shifts (ports, hosts, env var names), edit `task_prompts/11_env_switching.md` to reflect new defaults. Keep plan/tracker/AGENTS consistent. 
