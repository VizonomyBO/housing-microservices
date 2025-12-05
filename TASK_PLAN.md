# Task Plan: Full AWS Deployment + Local Compose Client

_Plan auto-approved per AGENTS.md; tracker will mirror progress and both files are temporary._

## Summary
Deploy the ingestion stack to AWS (using `terraform.tfvars` or a suffixed variant if collisions reappear), run the microservices locally via docker compose pointing to the AWS resources, and exercise the full curl flow per `TASK_DEFINITION.md` (login → upload via ingest API → attach → chat + SSE). Compose should ideally reuse existing profiles by toggling flags rather than custom files.

**New requirement (May 2025):** Automatically provision the EC2 SSH key pair inside Terraform so automation on this workstation can destroy/recreate the instance, capture the generated `.pem`, and immediately run the remote database bootstrap without manual SSH setup.

## Session Focus – 2025‑01‑?? (Steps 7–9: Auth UUID Alignment + AWS Verification)
- **Scope:** Resolve the `/v1/documents` empty listing by ensuring every component—auth-service, Lambdas, shared_data_layer, and agent-api—shares the same UUID string per user. This session owns tracker Steps 7–9: fix auth identity, prove `/v1/documents` works in AWS mode, and capture the curl walkthrough evidence (LocalStack remains deferred per user instructions).
- **Primary blocker:** Auth-service still persists numeric `user_id` values while ingestion Lambdas promote them to UUIDs via `int_to_uuid`, so listings filter on the wrong key. Tokens, refresh rows, and demo seeds all assume integers.

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
7. **Run Compose Locally** – Launch services via docker compose (with override/flag) ensuring they connect to AWS DB + AWS ingestion endpoints; confirm health across agent-api, auth-service, user-service, marker-service.
8. **Enforce Attachment Safety (Plan §5)** – Update `agent-api` attachment routes/services to block non-active documents, cover with automated tests, and document the error semantics.
9. **Manual Curl Walkthrough** – Follow docs/runbooks: login, request presigned upload from API Gateway, push sample document to S3, poll until active, attach, run SSE chat; capture outputs/logs and feed updates back into runbooks.
10. **LocalStack Verification** – Bring up the LocalStack-based stack (terraform, docker compose, pytest, curl flow, `scripts/prod_smoke_check.sh`) to ensure the ingestion pipeline works outside AWS.
11. **AWS Verification** – Repeat the terraform/apply as needed, run the compose stack in AWS mode, execute curl + smoke scripts end-to-end, and confirm documents activate plus SSE events fire.
12. **Quality Gates & Cleanup** – Run `uv run ruff format`, `uv run ruff check --fix`, `uv run ty check`, and `uv run pytest -n auto`; once complete remove the plan + tracker files per AGENTS.md.

## Research Notes / Sources
- AWS EC2 key pairs cannot be recovered; private keys must be generated client-side and stored securely ([AWS docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html)).
- Terraform can generate SSH keys using `tls_private_key` and register them via `aws_key_pair` for EC2 access without manual `.pem` handling ([Terraform AWS key pair resource](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/key_pair), [`tls_private_key` resource](https://registry.terraform.io/providers/hashicorp/tls/latest/docs/resources/private_key)).
