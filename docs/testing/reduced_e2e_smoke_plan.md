# Reduced Profile E2E Smoke Plan

## Overview
- **Persona**: A municipal housing analyst (“Ava”) who must upload vetted documents, attach them to a working session, and query them through the reduced-scope Agent API (text-only, no Valkey).
- **Objective**: Validate that registration, authentication, markdown uploads, attachment management, pillar-aware chat prompts, and LocalStack-backed dependencies all work together when the stack runs with `STACK_PROFILE=reduced`.
- **Entry conditions**:
  - Root compose stack is running with `COMPOSE_PROFILES=reduced`, `SERVICE_MODE=reduced`, and `USE_LOCALSTACK=1` per `docs/runbooks/reduced_scope_demo.md`.
  - LocalStack edge endpoint is reachable at `http://localhost.localstack.cloud:4566` (port 4566 exposed) so SDK calls and any future S3 usage can ride on the recommended hostname for bucket routing.\
    _Reference_: LocalStack endpoint guidance stresses exposing 4566 and using the wildcard DNS names when containers run in the same network. [LocalStack endpoint doc](https://docs.localstack.cloud/references/network-troubleshooting/endpoint-url/).  
  - LocalStack-aware clients (future fixtures/helpers) read `AWS_ENDPOINT_URL` so boto3 or `awslocal` talk to LocalStack instead of public AWS. [LocalStack boto3 doc](https://docs.localstack.cloud/aws/integrations/aws-sdks/python-boto3/).
- **Exit criteria**: Automation reports PASS when every API call succeeds, assertions on chat responses clear, and LocalStack health + attachments listing confirm the session state. Failures emit structured diagnostics (JSON blob plus log path) for the operator.

## Scenario Matrix
| # | Action | Endpoint / Command | Capability exercised | Assertions |
|---|--------|--------------------|----------------------|------------|
| 1 | Register Ava | `POST auth-service /v1/auth/register` | Auth microservice + data layer | 201 status, response includes `user.id`, `country_code=USA`. |
| 2 | Login Ava | `POST /v1/auth/login` | JWT issuance, refresh cookies | 200 status, capture `access_token`, `refresh_token`. |
| 3 | Bootstrap conversation | Helper module creates deterministic UUID via `uuid5(NAMESPACE_URL, f"reduced-e2e-{user_id}")` and upserts a `conversations` row (country `USA`). | Shared data layer + reduced runtime assumptions | Conversation row exists before attachments to avoid 404. Record ID for downstream steps. |
| 4 | Upload Policy Memo | `POST /v1/documents/upload` (Document A) | Markdown ingestion, dedupe hashing | 201 status, `status=COMPLETED`, `content_hash` matches fixture. |
| 5 | Upload Ledger | `POST /v1/documents/upload` (Document B) | Numerical data ingestion | 201 status, chunk created, message includes ingestion metadata. |
| 6 | Upload KPI Table | `POST /v1/documents/upload` (Document C) | Structured table as markdown | 201 status. |
| 7 | Attach Policy + Ledger | `POST /v1/conversations/{conversation_id}/attachments` (twice) | Attachment pipeline, reduced-scope filtering | 201 status for text docs, confirm listing shows both. |
| 8 | Optional: auto-attach base doc | same endpoint with `auto_attach_base_docs=true` | Auto attachment fallback | Response contains `auto_attached` IDs if seeded docs exist. |
| 9 | Simple QA prompt | `POST /v1/chat` (blocking) referencing policy doc | Retrieval + citation | Response contains phrase from Document A plus citation metadata pointing at uploaded doc. |
| 10 | Propositive reasoning prompt | `POST /v1/chat` referencing Documents A+B | Cross-doc reasoning | Response mentions two interventions and references both docs. |
| 11 | Numerical aggregate prompt | `POST /v1/chat` referencing ledger | Numeric sum check | Response sum equals expected ledger total and cites ledger doc. |
| 12 | SQL-style grouping prompt | `POST /v1/chat` referencing KPI table (Document C) | Table reasoning | Response contains grouped metrics (per city) and highlights the highest KPI. |
| 13 | Pillar snapshot | `GET /v1/conversations/{conversation_id}/pillars` | Pillar service + runtime | Returns answers generated during uploads (if available); otherwise plan records follow-up. |
| 14 | LocalStack health check | `curl http://localhost:4566/_localstack/health` | LocalStack readiness | JSON shows `status: running` for S3/EventBridge mocks. [LocalStack internal endpoints](https://docs.localstack.cloud/references/internal-endpoints/). |
| 15 | Cleanup (optional) | Helper detaches docs / deletes conversation | Idempotency for reruns | Ensures fixture reruns do not accumulate orphan state.

## Data Fixtures
### Document Catalog
| Alias | Canonical name | Format | Access scope | Key facts | Expected citations |
|-------|----------------|--------|--------------|-----------|--------------------|
| `DOC_POLICY` | “Metro Housing Continuity Memo – Q2 FY25” | Markdown narrative (headings + bullet points) | `user_shared` | - Emergency voucher expansion from 3 to 5 districts.\- Rent relief cap lowered to 32% income.\- Pilot requires monthly KPI email. | Use slug `doc_policy` and cite sections “Voucher Expansion” or “Rent Guardrails”. |
| `DOC_LEDGER` | “FY25 Rental Assistance Ledger (Q2 extract)” | Markdown table (City, Program, Amount USD, Households) | `user_shared` | Provide six rows; total = **$7.35M**, highlight District 9 = $1.8M. | Chat aggregate should name District 9 + $7.35M total. |
| `DOC_KPI` | “Metro KPI Snapshot – April 2025” | Markdown table (City, KPI, Value, Trend) plus summary paragraph | `user_shared` | Include KPIs for Harbor City, Lakeview, Southridge; highest KPI = Harbor City 87. | SQL-style grouping prompt expects Harbor City as highest, plus grouping counts. |

**Metadata conventions**
- `country_code`: `USA`, `language`: `en` for all user docs.
- `owner_user_id`: Ava’s UUID from registration.
- `tags`: `["reduced_e2e", "demo"]` to aid cleanup.
- `metadata`: add `{"scenario":"reduced_e2e", "document_alias":"DOC_POLICY"}` etc for quick lookups.
- Save fixture markdown under `services/agent-api/tests/data/reduced_e2e/<alias>.md` (Task 02 deliverable).

### Prompt & Expectation Matrix
| Prompt ID | Question | Capability | Expected answer traits | Validation logic |
|-----------|----------|------------|------------------------|------------------|
| `Q_SIMPLE_QA` | “What two guardrails did the latest housing memo add for voucher expansion?” | Simple QA | Mentions voucher district count + rent cap 32% | Regex for “five districts” and “32%” plus citation referencing `DOC_POLICY`. |
| `Q_REASON` | “Suggest two interventions that combine the policy memo and ledger insights to help District 9 renters.” | Propositive reasoning | Two bullet/numbered ideas referencing doc facts (e.g., shift $0.5M, enforce KPI emails). | Check response includes “District 9” and both doc aliases present in metadata/citations. |
| `Q_AGGREGATE` | “Sum the total rental assistance disbursed this quarter and highlight the highest-funded city.” | Numerical aggregate | Total `$7.35M`, highest District 9 $1.8M | Parse numbers (decimal tolerance 0.01) and confirm doc citation. |
| `Q_SQL` | “Group KPI values by city and call out whoever exceeds 80.” | SQL-style grouping | Mentions each city once, highlights Harbor City 87. | Compare number of city mentions against table, ensure “Harbor City” + “87” present. |

_All prompts run in blocking mode to keep assertions simple; streaming coverage already exists in reduced smoke tests._

## Automation Architecture
1. **Entry point**: `services/agent-api/scripts/run_reduced_e2e_smoke.py` executed via `uv run python ...`. Script orchestrates sequential stages above and exits non-zero on the first hard failure.
2. **Modules** (to be introduced in Tasks 02–03):
   - `reduced_e2e_fixtures.py`: loads markdown + scenario manifest, computes SHA-256 hashes for dedupe, exposes dataclasses for documents/prompts.
   - `reduced_e2e_client.py`: wraps `httpx.AsyncClient` for auth + Agent API calls, handling retries and structured logging.
   - `conversation_bootstrap.py`: uses shared data layer session (via `uv` + `.venv`) to upsert the deterministic conversation row for the authenticated user. This avoids creating bespoke HTTP endpoints solely for tests.
   - `localstack_probe.py`: polls `/_localstack/health` and optional `awslocal s3 ls` to confirm buckets once we start persisting artifacts. [LocalStack internal endpoints](https://docs.localstack.cloud/references/internal-endpoints/).
3. **Configuration**:
   - **Environment**: script reads `.env` (same as compose), honoring `AUTH_SERVICE_PORT`, `AGENT_API_PORT`, `LOCALSTACK_EDGE_PORT`, `AWS_ENDPOINT_URL`, `STACK_PROFILE`.
   - **LocalStack defaults**: prefer `AWS_ENDPOINT_URL=http://localhost.localstack.cloud:4566` so fixture helpers that eventually rely on boto3 inherit the recommended host. [LocalStack boto3 doc](https://docs.localstack.cloud/aws/integrations/aws-sdks/python-boto3/).
   - **Conversation ID**: `CONVERSATION_UUID=uuid5(NAMESPACE_URL, f"reduced-e2e-{user_id}")` stored in tracker JSON for reuse; Task 02 helper will insert if missing and reuse on reruns.
4. **Execution flow**:
   - Stage runner prints each action with emoji (✅/❌) plus latency; on failure, dumps HTTP request/response payloads to `logs/reduced_e2e/<timestamp>.json`.
   - Summaries persist to `logs/reduced_e2e/latest_report.json` so CI can parse status.
5. **Reporting**: script returns exit code 0 on success, non-zero otherwise, and writes a markdown recap block for release notes (Task 05 can embed in docs).

## Validation Strategy
1. **Stack prep** (run from repo root):
   ```bash
   STACK_PROFILE=reduced \
   COMPOSE_PROFILES=reduced \
     docker compose --profile reduced up --build agent-api
   ```
   Confirm Agent API, auth-service, and LocalStack all healthy (per runbook + LocalStack endpoint doc).
2. **Smoke runner**: prefer the Compose wrapper so environment prep, health checks, and CLI execution happen automatically:
   ```bash
   make reduced-e2e-smoke                # wraps scripts/run_reduced_e2e_compose.sh
   ```
   - Pass additional CLI options via `ARGS`, e.g., `make reduced-e2e-smoke ARGS="--skip-pillars"`.
   - Set `KEEP_STACK=1` to keep containers alive for debugging or omit it to have the wrapper tear everything down.
   - The wrapper copies `.env` from `env.example` when missing, starts the reduced + LocalStack profile, probes `/health` + `/v1/health`, runs the Typer CLI inside the `agent-api` container, then collects the JSON summary at `/app/logs/reduced_e2e_smoke.json`.
   - Direct invocation (`uv run python scripts/run_reduced_e2e_smoke.py ...`) still works from `services/agent-api` if you already have the stack running manually.
3. **LocalStack verification**: script (or operator) calls `curl http://localhost:4566/_localstack/health | jq` and surfaces failure states in summary. [LocalStack internal endpoints](https://docs.localstack.cloud/references/internal-endpoints/).
4. **Quality gates**: Regardless of outcome, continue to run `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto` before handing off (per `AGENTS.md`).
5. **Failure triage**: On error, review the JSON log for the first failing stage, inspect HTTP traces, and re-run with `--verbose-http` to log headers/bodies (redacting tokens).

### CI reference snippet
```yaml
name: reduced-e2e-smoke
on:
  workflow_dispatch:
  pull_request:
    paths:
      - services/agent-api/**
      - docker-compose.yml
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Reduced profile E2E smoke
        env:
          KEEP_STACK: 0
        run: make reduced-e2e-smoke
```
This job mirrors the local workflow and can be embedded in a larger pipeline when Task 05 expands documentation.

## Risks & Follow-ups
1. **Conversation lifecycle**: No public HTTP endpoint provisions conversations today. Task 02 must ship a helper that creates one via shared data layer. If a public API later appears, update this plan + checklist immediately so Task 03 swaps helpers for HTTP calls.
2. **LLM nondeterminism**: Prompts rely on textual heuristics (keywords, numeric sums). Keep tolerances loose (e.g., decimal comparisons) and assert on structured citation metadata rather than full strings.
3. **LocalStack drift**: Endpoint hostnames/ports occasionally change (see LocalStack networking guidance). Keep `AWS_ENDPOINT_URL` defaulted and document overrides; update plan if LocalStack v5 introduces breaking DNS changes.
4. **Data reset requirements**: Duplicate uploads or lingering attachments can cause dedupe responses. Provide `--reseed-docs` flag plus instructions for wiping conversation attachments.
5. **Checklist hygiene**: If future tasks skip scenario steps (e.g., drop SQL prompt) or add new documents, update `epic-reduced-e2e/CHECKLIST.md` **and** append a Handoff note to this task file explaining the delta so Task 03–05 inherit accurate scope.
