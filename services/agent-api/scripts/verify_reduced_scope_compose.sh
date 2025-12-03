#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR=$(cd "$(dirname "$0")/.." && pwd)
REPO_ROOT=$(cd "$SERVICE_DIR/../.." && pwd)
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

echo "Validating root docker compose config (reduced profile)"
(cd "$REPO_ROOT" && docker compose --profile reduced -f "$COMPOSE_FILE" config >/dev/null)

echo "Running reduced-scope smoke tests"
cd "$SERVICE_DIR"
uv run pytest -k reduced_scope_smoke

echo "Reduced-scope compose smoke suite completed"
