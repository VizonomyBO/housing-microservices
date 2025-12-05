# Task Tracker – AWS Deploy + Local Compose Client

| # | Status | Step | Notes |
|---|--------|------|-------|
| 1 | [x] | Prep & artifact check (lambda zips present). | Rebuilt shared layer via `build_shared_data_layer.sh` using `services/agent-api/.venv` python; `ArchaaS/lambdas/shared_layer.zip` now exists alongside other lambda zips. |
| 2 | [x] | Terraform apply prod (or suffix variant) to provision AWS stack. | Applied `terraform apply -auto-approve -var-file=terraform.v2.tfvars` in workspace `prod` with AWS creds; imported pre-existing lambda after timeout and completed apply. Outputs captured (API: https://gs6w1i52n4.execute-api.us-east-1.amazonaws.com/dev2, buckets `vizonomy-v2-raw-docs-dev2-4fd5a20a` / `vizonomy-v2-processed-artifacts-dev2-4fd5a20a`, DB host 172.31.8.64, EC2 public IP 44.216.103.232). |
| 3 | [x] | Configure compose env/flags for AWS endpoints. | Updated `.env.prod.aws` with Terraform output values (API Gateway ingest URL, AWS buckets, remote Postgres connection strings, localhost agent/auth base URLs) so docker compose + smoke scripts target the AWS stack. |
| 4 | [x] | Automate EC2 key management in Terraform + regenerate instance. | Added `tls_private_key` + `aws_key_pair` resources, persisted the PEM to `ArchaaS/dist/`, and re-applied terraform so new instances auto-wire SSH + security groups without manual keys. |
| 5 | [x] | Provision script glue (terraform destroy/apply + DB bootstrap). | Implemented `scripts/provision_remote_stack.sh` to wrap terraform workspace init/apply, patch `.env.prod.aws`, and trigger remote DB setup end-to-end. |
| 6 | [x] | Tooling Python environment for automation scripts. | Added `requirements.tooling.txt`, `.venv.tooling`, and `scripts/ensure_tooling_env.sh`; `scripts/setup_remote_databases.sh` now uses that shared env to run shared_data_layer migrations + auth bootstrap. |
| 7 | [ ] | Run compose locally against AWS resources. | |
| 8 | [x] | Enforce attachment safety in `agent-api` + tests. | Added ingestion-stage details to the 409 response for `/v1/conversations/{id}/attachments` and introduced `test_rejects_document_until_ingestion_complete` to prove documents stay unattached until `status=active`/`stage=activate`. |
| 9 | [ ] | Manual curl walkthrough (upload → attach → SSE). | |
|10 | [ ] | LocalStack verification (terraform, compose, smoke). | |
|11 | [ ] | AWS verification (terraform apply, curl, smoke) or capture blockers. | |
|12 | [ ] | Cleanup + quality gates (ruff/ty/pytest) then remove plan/tracker. | |
