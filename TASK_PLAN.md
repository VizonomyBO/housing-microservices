# Task Plan: Full AWS Deployment + Local Compose Client

_Plan auto-approved per AGENTS.md; tracker will mirror progress and both files are temporary._

## Summary
Deploy the ingestion stack to AWS (using `terraform.tfvars` or a suffixed variant if collisions reappear), run the microservices locally via docker compose pointing to the AWS resources, and exercise the full curl flow per `TASK_DEFINITION.md` (login → upload via ingest API → attach → chat + SSE). Compose should ideally reuse existing profiles by toggling flags rather than custom files.

**New requirement (May 2025):** Automatically provision the EC2 SSH key pair inside Terraform so automation on this workstation can destroy/recreate the instance, capture the generated `.pem`, and immediately run the remote database bootstrap without manual SSH setup.

## Session Focus – 2025‑01‑?? (Steps 7–9: Auth UUID Alignment + AWS Verification)
- **Scope:** Resolve the `/v1/documents` empty listing by ensuring every component—auth-service, Lambdas, shared_data_layer, and agent-api—shares the same UUID string per user. This session owns tracker Steps 7–9: fix auth identity, prove `/v1/documents` works in AWS mode, and capture the curl walkthrough evidence (LocalStack remains deferred per user instructions).
- **Primary blocker:** Auth-service still persists numeric `user_id` values while ingestion Lambdas promote them to UUIDs via `int_to_uuid`, so listings filter on the wrong key. Tokens, refresh rows, and demo seeds all assume integers.

### Session Checklist – 2025‑01‑?? (Step 8 deep dive)
1. **Prep remote auth DB** – Re-run `scripts/setup_remote_databases.sh` (leveraging `.venv.tooling`) so the migrated UUID schema + demo reseed land in AWS (`docs/runbooks/prod_setup.md` §3.3 for env vars).
2. **Rebuild & restart compose (AWS mode)** – Use `.env.prod.aws` with `docker compose -f docker-compose.yml -f docker-compose.prod.override.yml up -d --build auth-service user-service agent-api` so refreshed tokens flow through agent-api (`docs/runbooks/prod_setup.md` §4.2).
3. **AWS curl walkthrough** – Follow `docs/runbooks/prod_setup.md` §5 (or `/tmp/aws_flow.sh`) to:
   - Fetch demo token, confirm JWT `user_id` is UUID.
   - Upload sample PDF through API Gateway, poll `/v1/documents?content_hash=…` until `active`.
   - Attach the document to a conversation and capture SSE logs.
4. **Tracker updates + evidence** – Record commands/output snippets in `TASK_PLAN_PROGRESS.md` once `/v1/documents` shows the ingested doc; defer Step 9 (smoke script) per user note unless time allows.
5. **Lambda layer strategy (Dec 2025 directive)** – Per the latest user instruction we will **stop trimming per-function dependencies** and instead rebuild each ingestion Lambda so it always includes both shared layers (`aws_lambda_layer_version.python_deps`, `aws_lambda_layer_version.shared_data_layer`). Treat this as a hard requirement for Step 8: whenever layers change, rerun the full rebuild/terraform/apply sequence so every Lambda picks up the “bloated” bundle (common helper code + dependencies) even if the function only needs a subset. Optimization is explicitly deferred until after we prove the pipeline works end-to-end.
6. **State-machine data retention (Dec 2025 directive)** – Capture the original document-upload payload at the top of `document_ingestion_workflow.asl.json` (e.g., `Pass` state that writes `$.request = $`) and reference optional inputs such as `callback_url` from `$.request`. This keeps DeadLetter / EmitFailureEvent / ingestion_finalizer from crashing when later tasks overwrite the root input, matching AWS Step Functions guidance on `ResultPath`.
7. **AWS run discipline** – `/tmp/aws_flow.sh` uploads a document every invocation. After a timeout or failure, **do not re-upload**; instead continue polling `/v1/documents?content_hash=…` with the last hash, inspect the existing Step Functions execution via `aws stepfunctions describe-execution`, and pull Lambda CloudWatch logs. Only register a new document once we intentionally reset the test or change inputs.

## Session Focus – 2025‑02‑?? (Step 9: AWS Smoke Script + Evidence)
- **Scope:** Finish tracker Step 9 by running the documented AWS curl walkthrough plus `scripts/prod_smoke_check.sh` against the real stack (no LocalStack fallback this round). Compose already targets AWS; reuse `.env.prod.aws` as-is.
- **Plan references:** `docs/runbooks/prod_setup.md` §§5–6 (curl + smoke walkthrough), `scripts/prod_smoke_check.sh` inline docs, and `prod_sample_run.json` for prior evidence expectations.
- **Key tasks:**
  1. Generate a unique PDF for the run (e.g., copy `/tmp/sample.pdf` and append a timestamp) so ingestion bypasses content-hash dedupe.
  2. Execute the manual curl flow end-to-end (login, upload, poll `/v1/documents`, attach, SSE). Capture output snippets plus doc/conversation IDs for the tracker.
  3. Run `scripts/prod_smoke_check.sh` in AWS mode; if it initially times out, inspect Step Functions + document status, adjust the helper (poll windows, dedupe bypass) per findings, and re-run until it succeeds.
  4. Update `prod_sample_run.json` with fresh evidence (doc IDs, timestamps, SSE summary) and log the filesystem paths under `/tmp/aws_ingest_logs/` (or new dir) for reviewers.
  5. Record results—including commands, hashes, and any tweaks—in `TASK_PLAN_PROGRESS.md` row #9 so the next session can move on to Step 10+.
  6. Quirk note (Dec 2025): The old test PDFs were corrupt and triggered “No /Root object” placeholder content. Use the real PDF at `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf` (or a timestamped copy) for AWS smoke. Presigned uploads require parsing the fields safely and preserving `Content-Type`; see `docs/runbooks/prod_setup.md` and `scripts/prod_smoke_check.sh` for the fixed curl pattern. Evidence for the successful AWS smoke: doc `bae6eef5-7776-4a78-9333-dfb61d8ec65f`, conversation `e079ab22-b664-5d41-9d34-320e1b3ff204`, log `/tmp/aws_smoke_step9/prod_smoke_check_1764941879.log`.

### Ordered Steps (auto-approved for Session Scope)
1. **Reconfirm tracker + scope.** Keep Step 7 focused on schema + token changes, Step 8 on compose verification, Step 9 on AWS curls; annotate tracker as milestones finish so the next session can resume quickly.
2. **Research UUID storage + migration.** Capture references covering (a) SQLAlchemy’s backend-agnostic GUID type decorator and (b) Postgres’ `uuid-ossp` helpers for deterministic `uuid_generate_v5`, ensuring our conversions match the Lambda `int_to_uuid` logic.
3. **Update auth-service schema + data path.** Replace BigInt identifiers with UUID columns (users, refresh_tokens, foreign keys, Pydantic schemas, middleware, services, tests). Ensure new users default to UUIDv4 while legacy users migrate via deterministic v5 transformation so documents written by existing Lambdas continue to match.
4. **Reseed demo + automation scripts.** Update `scripts/setup_remote_databases.sh` (and any helper) so the remote auth DB reenforces UUID columns, installs `uuid-ossp`, reseeds the demo credentials with the canonical UUID, and keeps future applies idempotent.
5. **Align ingestion + agent-api edge cases.** Allow Lambdas to skip the int conversion once tokens already contain UUID strings while retaining a fallback for stale tokens.
6. **AWS verification + evidence.** Restart compose in AWS mode, reseed/obtain a demo token, run the curl walkthrough (docs/runbooks §5), ensure `/v1/documents` shows uploaded docs, attach them, capture SSE transcript, and note commands/output in the tracker.

### Risks / Mitigations
- **Layer rebuild permissions:** Previous Docker runs created root-owned artifacts, preventing cleanup. Mitigate by running `sudo rm -rf ArchaaS/lambdas/layer_package` if the script errors out, then rerun the build.
- **Terraform drift:** Another teammate might run Terraform concurrently. Always review the plan output before apply and be prepared to target only the layer + dependent lambdas.
- **Ingestion latency:** AWS Step Functions may take a few minutes; ensure polling logic has sufficient patience and capture logs if ingestion exceeds expectations.

### Research Sources
- Pydantic docs – “AWS Lambda” integration guide explains `no module named 'pydantic_core._pydantic_core'` stems from OS/CPU mismatches and recommends building dependencies for the Lambda platform (e.g., `--platform manylinux2014_x86_64` or a linux Docker image). <https://docs.pydantic.dev/latest/integrations/aws_lambda/>
- SQLAlchemy docs – Backend-agnostic GUID `TypeDecorator` ensures UUID columns stay compatible across PostgreSQL + SQLite, matching our need to store UUID primary keys while keeping unit tests on SQLite. <https://docs.sqlalchemy.org/en/20/core/custom_types.html#backend-agnostic-guid-type>
- PostgreSQL docs – `uuid-ossp` extension exposes `uuid_generate_v5(namespace uuid, name text)` so we can deterministically map legacy integer IDs to UUIDs that match the Lambda `int_to_uuid` helper. <https://www.postgresql.org/docs/current/uuid-ossp.html>

## Impacted Areas
- `ArchaaS/` Terraform modules + tfvars
- `.env.prod.aws` (or variant) for compose
- Possibly `docker-compose.prod.override.yml` / new profile flag to point at AWS
- Smoke/runbook artifacts (`prod_sample_run.json`, docs) if outputs change
- `scripts/setup_remote_databases.sh` plus any new provisioning helpers that glue terraform + DB bootstrap together
- Shared automation Python environment (`.venv.tooling`, `requirements.tooling.txt`, `scripts/ensure_tooling_env.sh`) used by Terraform + DB scripts

## Risks & Considerations
- Residual AWS resources may still exist; if apply fails with `EntityAlreadyExists`, switch to suffixed names (e.g., `project_name=vizonomy-v2`).
- Terraform needs `lambdas/shared_layer.zip`; verify artifact or rebuild before apply.
- Running compose against real AWS requires correct DB networking (ports must be reachable from this host) and IAM perms.
- Need to avoid repeated tear-downs to save time; keep services up between tests unless reconfiguration requires restart.
- Destroying and recreating the EC2 instance wipes its Postgres volumes; take backups or re-run migrations immediately after apply.
- Emitting a generated private key from Terraform is sensitive—ensure the file lands in a gitignored folder (`ArchaaS/dist/remote-ec2.pem`) and never gets committed or printed in logs beyond what automation needs.

## Execution Steps
1. **Prep + Artifact Check** – Ensure required lambda zips exist (`layer.zip`, `shared_layer.zip`); rebuild via existing scripts if missing.
2. **Terraform Apply (AWS)** – Run `terraform init`, select/create workspace (`prod`), execute `terraform apply -var-file=terraform.tfvars`. If name collisions occur, clone tfvars with `project_name`/`environment` suffix (e.g., `vizonomy-v2`, `dev2`) and reapply.
3. **Compose Configuration** – Update `.env.prod.aws` (or new flag) so compose services point at AWS resources; add a compose flag if needed to distinguish AWS mode (e.g., `STACK_PROFILE=aws`).
4. **Automated SSH Key Provisioning** – Update Terraform (`ec2.tf`, `variables.tf`, `outputs.tf`, `providers.tf`) to generate an RSA key pair when `ec2_key_pair_name` is unset, upload the public key via `aws_key_pair`, persist the private key to a gitignored file, and expose a sensitive output for automation scripts.
5. **Remote Provision Script** – Add `scripts/provision_remote_stack.sh` that (a) loads `.env.prod.aws` for AWS creds, (b) runs `terraform -chdir=ArchaaS apply -destroy` for the EC2 host when requested, (c) re-applies with `terraform.v2.tfvars`, (d) fetches the generated PEM, patches `.env.prod.aws` host/IPs, and (e) invokes `scripts/setup_remote_databases.sh`.
6. **Tooling Python Env** – Introduce a root-level uv-managed environment (`.venv.tooling`) plus `requirements.tooling.txt`/`scripts/ensure_tooling_env.sh` so automation scripts can install shared dependencies (shared_data_layer, auth-service requirements) without conflicting with service-specific virtualenvs.
7. **Run Compose Locally** – Launch services via docker compose (with override/flag) ensuring they connect to AWS DB + AWS ingestion endpoints; confirm health across agent-api, auth-service, user-service (marker-service is legacy and now skipped).
8. **Enforce Attachment Safety (Plan §5)** – Update `agent-api` attachment routes/services to block non-active documents, cover with automated tests, and document the error semantics.
9. **Manual Curl Walkthrough** – Follow docs/runbooks: login, request presigned upload from API Gateway, push sample document to S3, poll until active, attach, run SSE chat; capture outputs/logs and feed updates back into runbooks (use the real PDF `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf` to avoid corrupt fixtures).
10. **AWS Verification** – Repeat the terraform/apply as needed, run the compose stack in AWS mode, execute curl + smoke scripts end-to-end, and confirm documents activate plus SSE events fire.
11. **Harden AWS-mode compose env for auth/user** – Point auth/user containers at the remote Postgres host via `.env.prod.aws`/overrides so JWT login works without manual tokens when targeting AWS (all `.env*` files may be updated as needed).
12. **Automate env switching** – Add scripts/templates so compose, tooling, and lambdas pick the right DATABASE_URL/auth endpoints when toggling between LocalStack and AWS (safe to touch `.env*` files).
13. **Deploy services to EC2 host** – Add automation to package and run agent-api/auth-service/user-service on the existing EC2 (same host as Postgres), using public IP/hostnames for DB and peer services and exposing required ports/security-group rules so they can later be moved off-box without code changes (marker-service is deprecated and excluded by default).
14. **LocalStack Verification (last)** – After AWS + EC2 deployment, bring up a LocalStack-based stack (or docker-based emulation if LocalStack Pro is unavailable) and rerun terraform, compose, curl flow, and `scripts/prod_smoke_check.sh`.
15. **Quality Gates & Cleanup** – Run `uv run ruff format`, `uv run ruff check --fix`, `uv run ty check`, and `uv run pytest -n auto`; once complete remove the plan + tracker files per AGENTS.md.

## Task 10 Plan – Harden AWS-mode compose for auth/user services (auto-approved)
_Plan auto-approved; per user direction keep plan/tracker files after completion._

- **Goal:** Ensure `auth-service` and `user-service` run locally against the AWS Postgres host so JWT login works without manual tokens when `USE_LOCALSTACK=0`.
- **Scope:** Update compose overrides/env (`docker-compose.prod.override.yml`, `.env.prod.aws`, related helpers) to point auth/user at the remote `auth_db` / `housing` databases on `52.207.140.87:5432`. Validate with `/v1/auth/login` and `/v1/health` using demo creds (`demo.client@example.com` / `ChangeMe!123`).
- **Impacted files:** `.env.prod.aws`, `docker-compose.prod.override.yml`, `services/auth-service` and `services/user-service` compose env wiring, any helper scripts sourcing `.env.prod.aws`, tracker (`TASK_PLAN_PROGRESS.md`), future prompt notes (`task_prompts/11_env_switching.md`) if defaults change.
- **Ordered steps:**
  1. Inspect current AWS-mode env/compose wiring for auth/user (`.env.prod.aws`, `docker-compose.prod.override.yml`) to confirm which DB host/DB names they use when `USE_LOCALSTACK=0`.
  2. Align auth/user DB env vars to the AWS Postgres host (`52.207.140.87`, `auth_db` for auth-service, `housing` where applicable) and ensure credentials come from `.env.prod.aws`; propagate any new vars to helper scripts that source this file.
  3. Restart only auth-service and user-service in AWS mode (no LocalStack) and verify health (`/v1/health`) plus login (`/v1/auth/login`) returns a JWT using the remote DB.
  4. Update tracker row #10 with commands/evidence; if env defaults change, append a brief delta note to `task_prompts/11_env_switching.md`.
  5. Re-run any affected smoke commands if necessary to confirm compose AWS mode remains healthy; document verification in the tracker.
- **Risks / mitigations:** Remote DB auth_db may be missing migrations—rerun `scripts/setup_remote_databases.sh` if login fails; compose may cache old env—force container recreate for auth/user; ensure we don’t disturb agent-api AWS wiring.
- **Sources:** Internal runbooks `docs/runbooks/prod_setup.md` (compose AWS mode, login curl) and existing compose override `.env.prod.aws` conventions.

## Task 11 Plan – Automate env switching between AWS and LocalStack (auto-approved)
_Plan auto-approved; per Dec 2024 directive keep plan/tracker files after completion._

- **Summary:** Provide a single toggle so compose, helper scripts, and lambdas can switch between AWS and LocalStack (or future local emulation) without manual `.env` edits. Defaults should favor the current AWS stack while keeping LocalStack ready for later tasks.
- **Impacted files:** `.env*` templates, `docker-compose*.yml` (env wiring), `scripts/prod_smoke_check.sh`, terraform/runbook helpers under `scripts/` and `docs/runbooks/`, prompt updates under `task_prompts/12_ec2_services.md`, tracker files.
- **Risks / mitigations:** Divergent env names across services/scripts could drift; mitigate by centralizing variables in the toggle script and documenting required exports. Avoid breaking existing AWS defaults; verify AWS mode with a login curl before finishing.
- **Ordered steps (checkbox = tracker sync):**
  - [ ] Inventory env consumers (compose overrides, smoke/terraform/runbooks) and note required vars for AWS vs LocalStack.
  - [ ] Design and add the toggle (script + `.env.*.template` or similar) that exports the canonical set (DB URLs, service base URLs, `INGEST_BASE_URL`, `USE_LOCALSTACK`, AWS creds).
- [ ] Wire consumers to the toggle (compose, scripts, lambdas/templates) so they source the generated env without manual edits.
- [ ] Verify AWS mode minimally (login curl) and sanity-check LocalStack mode resolves variables; record commands/evidence.
- [ ] Update docs/runbooks + tracker row #11; note any new vars/paths in `task_prompts/12_ec2_services.md`.
- **Research sources:** Internal `docs/runbooks/prod_setup.md` (compose env expectations) and existing helpers (`scripts/prod_smoke_check.sh`, `.env.prod.aws`) for canonical variable names. No external references expected unless new tooling arises.

## Task 12 Plan – Deploy services to EC2 (auto-approved; keep plan/tracker per user directive)
_Plan auto-approved; keep plan/tracker files in place after completion for continuity._

- **Summary:** Package and run `agent-api`, `auth-service`, and `user-service` on the existing EC2 host that already runs Postgres. Marker-service is legacy/unused and should be skipped unless explicitly needed for a retrospective test. Use public hostnames/IPs for DB and peer services so they can be moved off-box later via env only. Expose required ports (agent-api 8000, auth 5001, user 5002, swagger 3000 if used) via security groups/iptables and automate start/stop/update.
- **Plan reference:** `task_prompts/12_ec2_services.md`, Task 12 section of `TASK_DEFINITION.md`, existing env toggle `scripts/use_env.sh aws`.
- **Impacted files:** New deploy helper under `scripts/` (e.g., `deploy_ec2_services.sh`), optional systemd/unit templates or compose override snippets, `.env.prod.aws`/`.env.active` (gitignored) for public endpoints, docs/runbooks for EC2 deployment notes, tracker (`TASK_PLAN_PROGRESS.md` row 12), follow-on prompts (`task_prompts/13_localstack_verification.md`, `task_prompts/14_cleanup_reset.md`) if env/ports change. Note: marker-service is legacy; do not include it in new deploys.
- **Risks / mitigations:** EC2 may lack uv/docker/systemd → add bootstrap steps; security groups may block ports → document required rules/CLI commands; long-lived services need log/venv isolation → prefer containers or systemd-managed uv runs; must avoid hardcoding private addresses so later relocation is env-only; ensure automation is idempotent and does not clobber Postgres data.
- **Ordered steps (checkbox = tracker sync):**
  - [x] Review `task_prompts/12_ec2_services.md`, current env/compose wiring, and DB/service endpoints to confirm required ports + env vars (DB at `52.207.140.87:5432`, API Gateway base, peer URLs).
  - [x] Decide packaging strategy (docker-compose vs systemd+uv) favoring reproducible deploys; outline env sourcing via `scripts/use_env.sh aws`/`.env.active` using public hosts.
  - [x] Implement automation (e.g., `scripts/deploy_ec2_services.sh` plus optional unit templates) that bootstraps dependencies on EC2, syncs env/config, builds or pulls images, runs services bound to public-facing hostnames/ports, and notes required SG/iptables updates (marker-service excluded unless explicitly opted in).
  - [x] Document start/stop/update + verification commands (health endpoints, auth login curl) for EC2; capture any SG changes and note marker-service deprecation.
  - [x] Update `TASK_PLAN_PROGRESS.md` row 12 with commands/evidence; propagate env/port changes to `task_prompts/15_localstack_verification.md` and `task_prompts/16_cleanup_reset.md` if needed (call out marker-service is legacy).

### New scope (user request, Dec 2025 — continues prior EC2 work)
- Continue from the completed EC2 deploy/smoke baseline and now: switch the converter to use MarkItDown in the ingestion pipeline (marker-converter Lambda) so PDFs are robustly parsed; rebuild layers/Lambdas as needed.
- Remove the legacy `services/marker-service` folder entirely and document its deprecation.
- Clean up placeholder/legacy documents in Postgres/S3 created during earlier failed runs.
- Refresh `scripts/prod_smoke_check.sh` defaults (use a reliable PDF, new ingest endpoint) and rerun full e2e on AWS/EC2 (upload → poll → attach → two-turn chat) until success.
- Update tracker/docs to reflect the new ingest endpoint/IP and the MarkItDown switch.

## Research Notes / Sources
- AWS EC2 key pairs cannot be recovered; private keys must be generated client-side and stored securely ([AWS docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html)).
- Terraform can generate SSH keys using `tls_private_key` and register them via `aws_key_pair` for EC2 access without manual `.pem` handling ([Terraform AWS key pair resource](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/key_pair), [`tls_private_key` resource](https://registry.terraform.io/providers/hashicorp/tls/latest/docs/resources/private_key)).
- Docker installation on Amazon Linux 2023: AWS SAM guide outlines updating packages, installing Docker CE, starting the service, and adding `ec2-user` to the docker group ([AWS docs](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-docker.html)).
- Docker Compose plugin install on Linux (preferred over standalone binary) via the Docker docs ([Docker docs](https://docs.docker.com/compose/install/linux/)).
- Systemd services can run Python apps inside a venv by pointing `ExecStart` at the venv’s Python binary instead of sourcing `activate` ([Stack Overflow](https://stackoverflow.com/questions/37211115/how-to-enable-a-virtualenv-in-a-systemd-service-unit)).
- Opening ports via security groups using the AWS CLI `authorize-security-group-ingress` command ([AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/ec2/authorize-security-group-ingress.html)).
