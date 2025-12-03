# Task 04 — LocalStack & AWS Toggle Integration

## System Snapshot
- The root Compose stack (Task 02) now defines a LocalStack container and profiles, and Task 03 standardized env variables (`USE_LOCALSTACK`, AWS creds, etc.).
- Services that interact with AWS (e.g., S3 uploads, SES, SQS, EventBridge placeholders) still assume real AWS endpoints and may not honor the new toggle.
- There is no runtime mechanism to automatically route SDK calls to LocalStack when running locally, nor documentation describing the behavior.

## Goal
Implement the runtime wiring that lets developers switch between LocalStack (default for local Compose) and real AWS (when `USE_LOCALSTACK=0`). This includes:
- Updating each service to read the toggle and derive the correct AWS endpoints/regions.
- Ensuring shared libraries (if any) expose helpers for creating AWS clients with endpoint overrides.
- Documenting which AWS services are emulated and verifying LocalStack compatibility.

## Must Read / Inspect Before Coding
1. `docs/infrastructure/root_compose_plan.md` sections on LocalStack strategy.
2. The finalized `.env.example` (Task 03) to understand variable names.
3. Service code that talks to AWS:
   - Search for `boto3`, `botocore`, `aws`, `s3`, `ses`, `sns`, `sqs`, etc. inside `services/`.
   - Review helper modules (e.g., `services/agent-api/scripts/*`, other packages) for AWS interactions.
4. LocalStack docs on configuring endpoint URLs, credentials, and service availability.

## Implementation Scope & Files
- Introduce a shared utility (if helpful) under `packages/` or within each service to build AWS clients using env-driven settings:
  - Example envs: `USE_LOCALSTACK`, `LOCALSTACK_HOST`, `LOCALSTACK_EDGE_PORT`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
- Update each microservice that calls AWS to:
  - Read the new toggle.
  - Redirect endpoints to LocalStack when `USE_LOCALSTACK=1`.
  - Fall back to real AWS endpoints when disabled.
- Ensure LocalStack service definitions expose needed ports in `docker-compose.yml` and that dependent services include `depends_on` entries.
- Add smoke tests or CLI checks (where feasible) that confirm LocalStack wiring works (e.g., hitting a stubbed S3 bucket).
- Capture any AWS features that cannot be mocked easily and document required follow-up work.

## Step-by-Step Instructions
1. **Inventory AWS usage per service**:
   - Catalog each AWS SDK call (S3, SES, SQS, etc.) and note where configuration is loaded.
   - Decide whether a shared helper (e.g., `packages/aws_utils.py`) should handle endpoint construction.
2. **Implement endpoint toggle**:
   - For each service, update its config to derive `AWS_ENDPOINT_URL` (or service-specific endpoints) from the env toggle.
   - When `USE_LOCALSTACK=1`, point SDK clients to `http://localstack:4566` (or the port defined in Compose) and use the dummy credentials from `.env`.
   - When `USE_LOCALSTACK=0`, default to AWS’s standard endpoints and credentials.
3. **Wire Compose dependencies**:
   - Ensure services depending on LocalStack list it in `depends_on` and share the same network.
   - Expose LocalStack ports on the host only if required (document any firewall considerations).
4. **Validate locally**:
   - Bring up the reduced stack with LocalStack enabled, create any prerequisite resources (e.g., `awslocal s3 mb s3://demo-bucket`), and run a minimal integration (upload a file, send a fake email log, etc.).
   - Record commands and outcomes in the task log.
5. **Document gaps**:
   - If certain AWS services are not yet implemented in the codebase, note that in the plan and add TODO comments referencing this task.

## Definition of Done
- Every service that touches AWS honors the `USE_LOCALSTACK` (or similar) toggle and routes traffic through LocalStack when enabled.
- LocalStack container is reachable by the services (network + env), and basic smoke verification is documented (commands + results).
- The root Compose file exposes any required LocalStack ports and ensures dependent services wait for it to be healthy.
- TODOs or follow-up tasks are added for AWS features that remain unimplemented.
- Task 04 checkbox is updated in the checklist, with supporting notes in `services/agent-api/logs/task_04`.
