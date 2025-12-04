# Production (Reduced Scope) Runbook

This guide captures everything you need to bring up the reduced-scope backend for a real frontend demo, whether you are pointing at LocalStack or real AWS services.

## 1. Prerequisites
- Ubuntu/AlmaLinux host or EC2 instance with Docker Engine v25+ and Compose V2 (`docker compose`).
- Open outbound internet access for OpenAI/Voyage API calls.
- A copy of `.env.prod` populated with production secrets (see below).
- Optional but recommended: `jq` (used by the verification script) and `curl`.

## 2. Prepare `.env.prod`
1. Copy the template and edit secrets:
   ```bash
   cp env.example .env.prod
   nano .env.prod            # replace every placeholder before running
   ```
2. Always set unique values for:
   - `POSTGRES_PASSWORD`, `AGENT_API_DB_PASSWORD`, `JWT_SECRET_KEY`, `SECRET_KEY`, `AUTH_SHARED_SECRET`.
   - `OPENAI_API_KEY`, `VOYAGE_API_KEY` (real paid accounts).
3. Optional networking tweaks:
   - If exposing behind an ALB/NGINX, update `AGENT_BASE_URL` / `AUTH_BASE_URL` to the public DNS name.
   - Keep the container ports (8000/5001) unless you also change `docker-compose.yml`.
4. Whenever you run commands that rely on these variables (Compose, smoke script, cURL helpers), export them into your shell with:
   ```bash
   set -a && source .env.prod && set +a
   ```
   This mirrors the `.env` file that Docker Compose reads and keeps CI-safe defaults in `.env.prod`.

## 3. LocalStack vs Real AWS
`USE_LOCALSTACK` is the single toggle:
- `USE_LOCALSTACK=1` (default) – Docker brings up the LocalStack container and all services talk to it. `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` can remain the dummy values shipped with `.env.prod`.
- `USE_LOCALSTACK=0` – The backend will call real AWS endpoints. **You must** provide real AWS credentials + region and leave `AWS_ENDPOINT_URL` blank so boto/httpx auto-discover the real services.
- Nothing else changes: OpenAI/Voyage LLM calls run the same way in both modes.

## 4. Start the Backend
```bash
set -a && source .env.prod && set +a
COMPOSE_PROFILES=reduced,ops docker compose --profile reduced up -d --build
COMPOSE_PROFILES=reduced,ops docker compose --profile reduced logs -f agent-api
```
- `db-init` runs migrations + seeds the reduced-scope fixtures.
- Health checks to verify readiness:
  ```bash
  curl $AGENT_BASE_URL/health
  curl $AGENT_BASE_URL/v1/health
  curl $AUTH_BASE_URL/v1/health
  ```

## 5. Create/Verify Demo User & Documents
The reduced stack seeds four sample documents automatically (Housing Stability overview, Voucher Guardrails fiscal memo, District 9 ledger, and a KPI dashboard table). Those sources contain the guardrail, intervention, and KPI data referenced by `scripts/prod_smoke_check.sh`, so the smoke answers are grounded in text. To ensure the demo user exists (and to reset their password), run:
```bash
curl -X POST "$AUTH_BASE_URL/v1/auth/register" \
     -H 'Content-Type: application/json' \
     -d "{\"email\":\"$PROD_DEMO_EMAIL\",\"username\":\"$PROD_DEMO_USERNAME\",\"password\":\"$PROD_DEMO_PASSWORD\",\"first_name\":\"$PROD_DEMO_FIRST_NAME\",\"last_name\":\"$PROD_DEMO_LAST_NAME\"}"
```
If the user already exists, the endpoint returns 409; ignore it.

## 6. Run the Prod Smoke Script
1. Ensure the stack is running (`docker compose ps`).
2. Execute the bundled verifier:
   ```bash
   set -a && source .env.prod && set +a
   ./scripts/prod_smoke_check.sh
   ```
3. The script:
   - Logs in with the demo user.
   - Creates a conversation and attaches all seeded documents.
   - Asks three questions (simple RAG, cross-doc reasoning, table/SQL) against `/v1/chat`. Quantitative prompts automatically fan out through the numerical/Polars planner—no need to mention “SQL” or “Polars” in the question.
   - Stores the responses, citations, and raw payloads in `prod_sample_run.json` (gitignored).
4. Open `prod_sample_run.json` to confirm the answers look correct before handing the backend to the frontend team.

## 7. Inspect Node-Level Logs
Because `.env.prod` forces `UVICORN_LOG_LEVEL=info`, each `/v1/chat` call emits `task_start/task_end` SSE events. **Refresh the auth token right before you stream** (tokens only last ~15 minutes):
```bash
set -a && source .env.prod && set +a
TOKEN=$(curl -sS -X POST "$AUTH_BASE_URL/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"login\":\"$PROD_DEMO_EMAIL\",\"password\":\"$PROD_DEMO_PASSWORD\"}" \
  | jq -r .access_token)
```
Then stream the request:
```bash
curl -N -H "Authorization: Bearer $TOKEN" -H 'Accept: text/event-stream' \
     -H 'Content-Type: application/json' \
     -d '{
           "thread_id":"...",
           "message":{
             "type":"user",
             "content":"Using the guardrail memo, District 9 ledger, and KPI dashboard, identify which zones exceed the 80-point trigger and outline a two-step plan that pairs arrears relief with voucher guardrails for those renters. Cite KPI values and dollar figures."
           },
           "constraints":{"country_code":"USA","auto_attach_base_docs":false}
         }' \
     "$AGENT_BASE_URL/v1/chat"
```
The `thread_id` is the conversation ID printed by `./scripts/prod_smoke_check.sh` (e.g., `[prod_smoke_check] Using conversation f233848f-8832-5969-9ca0-877f9e2af652`). The richer question above automatically routes through the numerical (Polars) subgraph—the router now detects KPI/threshold language without relying on explicit “SQL” hints—so you can watch every `task_start`/`task_end` event in the stream. A full sample transcript is available in [`docs/examples/prod_sse_walkthrough.md`](../examples/prod_sse_walkthrough.md).
You can also tail the compose logs:
```bash
COMPOSE_PROFILES=reduced,ops docker compose logs -f agent-api | grep informational_
```
Expect to see `input_normalizer`, `attachment_scope_loader`, `graph_retriever`, `graph_summarizer`, `router`, `informational_answer_synthesizer` for every chat message.

## 8. Tear Down / Reset
```bash
COMPOSE_PROFILES=reduced,ops docker compose --profile reduced down -v --remove-orphans
```
This removes all containers, volumes (including Postgres/LocalStack data), and stray networks.

## 9. Troubleshooting
| Symptom | Remedy |
| --- | --- |
| `db-init` fails with auth errors | Double-check DB passwords in `.env.prod` match `scripts/init-databases.sh`. Run `docker compose run --rm db-init` after fixing env vars. |
| `localstack` container flaps | Set `LOCALSTACK_DEBUG=1` and tail `docker compose logs -f localstack`. If talking to real AWS, ensure `USE_LOCALSTACK=0` and credentials are exported. |
| Smoke script exits early | Inspect `prod_sample_run.json` (partial file) and `docker compose logs agent-api`. Usually caused by missing demo docs—rerun `make reduced-e2e-smoke ARGS="--use-real-tools --verify-real-tools --cleanup-only"`. |
| Frontend CORS errors | Populate `CORS_ORIGINS` with the frontend domain once you’re ready to enforce browser calls. |

Refer back to this runbook whenever you need to recreate or reset the production demo environment.
