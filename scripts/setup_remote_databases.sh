#!/usr/bin/env bash
set -euo pipefail

# Bootstraps the remote Postgres instance that lives on the EC2 host
# provisioned by Terraform (creates the housing/auth_db databases,
# installs extensions, and runs migrations for both stacks).

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$ROOT_DIR/.env.prod.aws"}

if [[ -f "$ENV_FILE" ]]; then
  echo "Loading env vars from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Env file $ENV_FILE not found; relying on shell vars"
fi

"$ROOT_DIR/scripts/ensure_tooling_env.sh" &>/dev/null
TOOL_ENV="$ROOT_DIR/.venv.tooling"
TOOL_PY="$TOOL_ENV/bin/python"

REMOTE_DB_HOST=${REMOTE_DB_HOST:-${POSTGRES_HOST:-}}
if [[ "$REMOTE_DB_HOST" == "CHANGE_ME_EC2_PUBLIC_IP" ]]; then
  REMOTE_DB_HOST=""
fi
if [[ -z "${REMOTE_DB_HOST}" ]]; then
  if command -v terraform >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
    REMOTE_DB_HOST=$(terraform -chdir="$ROOT_DIR/ArchaaS" output -json summary 2>/dev/null \
      | jq -r '.ec2.public_ip // empty')
  fi
fi

if [[ -z "${REMOTE_DB_HOST}" ]]; then
  echo "ERROR: REMOTE_DB_HOST not set. Export it or ensure terraform+jq are available." >&2
  exit 1
fi

if [[ "${POSTGRES_HOST:-}" == "CHANGE_ME_EC2_PUBLIC_IP" ]]; then
  POSTGRES_HOST="$REMOTE_DB_HOST"
  if [[ -w "$ENV_FILE" ]]; then
    python3 - <<PY
from pathlib import Path
env_path = Path(r"$ENV_FILE")
text = env_path.read_text()
text = text.replace("POSTGRES_HOST=CHANGE_ME_EC2_PUBLIC_IP", "POSTGRES_HOST=$REMOTE_DB_HOST", 1)
env_path.write_text(text)
PY
    echo "Updated POSTGRES_HOST in $ENV_FILE"
  fi
else
  POSTGRES_HOST=${POSTGRES_HOST:-$REMOTE_DB_HOST}
fi

REMOTE_DB_PORT=${REMOTE_DB_PORT:-${POSTGRES_PORT:-5432}}
DB_ADMIN_USER=${REMOTE_DB_USER:-${POSTGRES_USER:-vizonomy_user}}
DB_ADMIN_PASSWORD=${REMOTE_DB_PASSWORD:-${POSTGRES_PASSWORD:-}}
HOUSING_DB=${REMOTE_HOUSING_DB_NAME:-${POSTGRES_DB:-housing}}
AUTH_DB=${REMOTE_AUTH_DB_NAME:-${AUTH_DB:-auth_db}}

if [[ -z "$DB_ADMIN_PASSWORD" ]]; then
  echo "ERROR: Database password not provided (POSTGRES_PASSWORD or REMOTE_DB_PASSWORD)." >&2
  exit 1
fi

PSQL_BASE=(psql -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$DB_ADMIN_USER")

echo "Ensuring databases exist on $REMOTE_DB_HOST:$REMOTE_DB_PORT..."
PGPASSWORD="$DB_ADMIN_PASSWORD" "${PSQL_BASE[@]}" postgres <<SQL
DO
\$\$
BEGIN
  PERFORM FROM pg_database WHERE datname = '${HOUSING_DB}';
  IF NOT FOUND THEN
    EXECUTE format('CREATE DATABASE %I OWNER %I', '${HOUSING_DB}', '${DB_ADMIN_USER}');
  END IF;
  PERFORM FROM pg_database WHERE datname = '${AUTH_DB}';
  IF NOT FOUND THEN
    EXECUTE format('CREATE DATABASE %I OWNER %I', '${AUTH_DB}', '${DB_ADMIN_USER}');
  END IF;
END;
\$\$;
SQL

echo "Installing extensions (vector) if missing..."
for db in "$HOUSING_DB" "$AUTH_DB"; do
  PGPASSWORD="$DB_ADMIN_PASSWORD" "${PSQL_BASE[@]}" "$db" -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
done

echo "Running shared_data_layer migrations on ${HOUSING_DB}..."
(
  cd "$ROOT_DIR"
  DATABASE_URL="postgresql+asyncpg://${DB_ADMIN_USER}:${DB_ADMIN_PASSWORD}@${REMOTE_DB_HOST}:${REMOTE_DB_PORT}/${HOUSING_DB}" \
    "$TOOL_PY" -m shared_data_layer.manage migrate >/dev/null
)

echo "Ensuring auth-service tables exist in ${AUTH_DB}..."
(
  cd "$ROOT_DIR/services/auth-service"
  DATABASE_URL="postgresql://${DB_ADMIN_USER}:${DB_ADMIN_PASSWORD}@${REMOTE_DB_HOST}:${REMOTE_DB_PORT}/${AUTH_DB}" \
    "$TOOL_PY" - <<'PY'
from app.config import Config
from app.database import init_db, create_tables

config = Config()
init_db(config)
create_tables()
print("Auth-service schema ready.")
PY
)

echo "Remote databases are ready for use."
