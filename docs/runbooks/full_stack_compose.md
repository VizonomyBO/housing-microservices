# Full Stack Compose Runbook

Use this guide when you need the entire microservices platform (auth, user, swagger, agent-api, marker-service, LocalStack, Valkey, telemetry) running locally through the root `docker-compose.yml`.

## 1. Prerequisites
- Docker 25.x with Compose V2 (`docker compose`).
- Git + bash-compatible shell.
- Sufficient resources (~6–8 GB RAM) for all services + LocalStack.
- Optional: [uv](https://github.com/astral-sh/uv) for running scripts/tests.

## 2. Environment Preparation
1. Copy the template and edit secrets:
   ```bash
   cp env.example .env
   ```
2. Key variables to review:
   - `STACK_PROFILE=full`
   - `COMPOSE_PROFILES=full,ops` (adds helper containers like `db-shell`).
   - `USE_LOCALSTACK=1` to emulate AWS. Set to `0` + supply real AWS credentials when you want to hit AWS directly.
   - Host ports (`AUTH_SERVICE_PORT`, `USER_SERVICE_PORT`, etc.) to avoid local conflicts.
3. Optional overrides belong in `.env.local` (gitignored). Source it before running Compose: `set -a; source .env.local; set +a`.

## 3. Launch Sequence
```bash
STACK_PROFILE=full \
COMPOSE_PROFILES=full,ops \
  docker compose --profile full up --build
```
- Services without profile entries (`postgres`, auth-service, user-service, swagger-service, localstack) start automatically.
- `db-init` runs once Postgres is healthy, ensuring both the reduced agent schema and auth DB migrations are applied.
- `marker-service`, `valkey`, and `otel-collector` join because the `full` profile is active.
- First builds can take several minutes; subsequent `up` commands reuse cached layers.

## 4. Verification Checklist
| Item | Command |
| --- | --- |
| Compose lint | `docker compose --profile full config` |
| Swagger health | `curl http://localhost:${SWAGGER_SERVICE_PORT:-3000}/health` |
| Auth health | `curl http://localhost:${AUTH_SERVICE_PORT:-5001}/health` |
| User health | `curl http://localhost:${USER_SERVICE_PORT:-5002}/v1/health` |
| Agent API health | `curl http://localhost:${AGENT_API_PORT:-8000}/health` |
| Marker health | `curl http://localhost:${MARKER_SERVICE_PORT:-8004}/health` |
| LocalStack | `curl http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health` |
| Valkey ping | `docker compose exec valkey valkey-cli ping` |

## 5. LocalStack Toggle
- **Local mode (default)**: `USE_LOCALSTACK=1` keeps `AWS_ENDPOINT_URL` pointing at the `localstack` container. Buckets (`RAW_DOCUMENTS_BUCKET`, `PROCESSED_BUCKET`) are created on startup and the smoke wrapper waits for `/_localstack/health` before running.
- **Real AWS**: set `USE_LOCALSTACK=0`, populate `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, (optional) `AWS_SESSION_TOKEN`, and clear `AWS_ENDPOINT_URL`. Restart any AWS-aware services (`docker compose restart agent-api marker-service`), and expect the reduced smoke wrapper to skip LocalStack entirely so every SDK call hits the real endpoints you configured.
- To inspect LocalStack resources, run `docker compose exec localstack awslocal s3 ls`.

## 6. Seeding & CLI Helpers
- `db-init` automatically seeds LangGraph demo data. Rerun it manually with `docker compose run --rm db-init` if you reset volumes.
- Use the CLI for ingestion/pillar tests:
  ```bash
  docker compose exec agent-api uv run agent_api.cli --help
  docker compose exec marker-service uv run python scripts/sample_ingest.py
  ```
- The `db-shell` profile keeps an interactive Postgres shell running: `docker compose --profile full,ops exec db-shell bash` → `psql ...`.

## 7. Observability
- OpenTelemetry collector exposes gRPC on `${OTEL_COLLECTOR_GRPC_PORT:-4317}` and HTTP on `${OTEL_COLLECTOR_HTTP_PORT:-4318}`. Point local SDKs at those ports to forward traces.
- Valkey is available on `${VALKEY_PORT:-6379}` for manual cache inspection.

## 8. Tear Down & Cleanup
```bash
docker compose --profile full down                # stop everything
docker compose --profile full down -v             # also delete Postgres/LocalStack/Valkey volumes
docker volume rm housing-microservices_localstack_data  # optional targeted cleanup
```
Remember to stop resource-intensive services when not in use to free CPU/RAM.

## 9. Troubleshooting
| Symptom | Action |
| --- | --- |
| Marker service cannot reach LocalStack | Check `USE_LOCALSTACK`, ensure `localstack` container is healthy, verify `AWS_ENDPOINT_URL` is set. |
| Agent API waiting on db-init | Confirm Postgres health (`docker compose logs postgres`). If necessary, rerun `docker compose run --rm db-init`. |
| Valkey refuses connections | Ensure the `full` profile is active and `VALKEY_PORT` isn’t already in use. |
| Ports 3000/5001/5002 busy | Override host ports in `.env` (e.g., `SWAGGER_SERVICE_PORT=3100`) before running Compose. |
| High resource usage | Start only what you need: `docker compose --profile full up agent-api marker-service localstack`. |

Keep this runbook alongside `docs/runbooks/reduced_scope_demo.md` so teammates know how to switch between the lightweight demo and the full platform.
