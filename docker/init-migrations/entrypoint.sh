#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-${POSTGRES_HOST:-postgres}}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-${POSTGRES_DB:-housing}}"
DB_USER="${DB_USER:-${POSTGRES_USER:-vizonomy_user}}"
DB_PASSWORD="${DB_PASSWORD:-${POSTGRES_PASSWORD:-postgres}}"
RETRIES="${RETRIES:-30}"
SLEEP_SECONDS="${SLEEP_SECONDS:-2}"

export PGPASSWORD="$DB_PASSWORD"

echo "Waiting for Postgres at ${DB_HOST}:${DB_PORT} (${DB_NAME})..."
for attempt in $(seq 1 "$RETRIES"); do
  if pg_isready -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -U "$DB_USER" >/dev/null 2>&1; then
    echo "Postgres is ready."
    break
  fi
  echo "Postgres not ready yet (attempt $attempt/$RETRIES); sleeping ${SLEEP_SECONDS}s..."
  sleep "$SLEEP_SECONDS"
done

if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -U "$DB_USER" >/dev/null 2>&1; then
  echo "Postgres did not become ready in time" >&2
  exit 1
fi

: "${DATABASE_URL:?DATABASE_URL is required for migrations}"

source /app/.venv/bin/activate

echo "Running Alembic migrations to ${REVISION:-head}"
uv run python /app/packages/shared_data_layer/src/shared_data_layer/manage.py migrate --revision "${REVISION:-head}"
echo "Migrations finished."
