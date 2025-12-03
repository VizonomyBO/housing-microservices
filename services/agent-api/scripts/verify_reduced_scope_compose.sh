#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR=$(cd "$(dirname "$0")/.." && pwd)
COMPOSE_FILE="$SERVICE_DIR/docker-compose.reduced.yml"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

echo "Validating docker compose config"
docker compose -f "$COMPOSE_FILE" config >/dev/null

echo "Running reduced-scope smoke tests"
cd "$SERVICE_DIR"
uv run pytest -k reduced_scope_smoke

echo "Reduced-scope compose smoke suite completed"
