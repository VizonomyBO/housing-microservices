#!/usr/bin/env bash
set -euo pipefail

# Bootstraps the remote Postgres instance that lives on the EC2 host
# provisioned by Terraform (creates the housing/auth_db databases,
# installs extensions, and runs migrations for both stacks).

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
DEFAULT_ENV_FILE="$ROOT_DIR/.env.active"
FALLBACK_ENV_FILE="$ROOT_DIR/.env.prod.aws"
ENV_FILE=${ENV_FILE:-}
if [[ -z "$ENV_FILE" ]]; then
  if [[ -f "$DEFAULT_ENV_FILE" ]]; then
    ENV_FILE="$DEFAULT_ENV_FILE"
  else
    ENV_FILE="$FALLBACK_ENV_FILE"
  fi
fi

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

echo "Installing uuid-ossp extension (auth DB)..."
PGPASSWORD="$DB_ADMIN_PASSWORD" "${PSQL_BASE[@]}" "$AUTH_DB" -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";' >/dev/null

echo "Ensuring auth-service user IDs are stored as UUIDs..."
PGPASSWORD="$DB_ADMIN_PASSWORD" "${PSQL_BASE[@]}" "$AUTH_DB" <<'SQL'
DO $$
DECLARE
    needs_migration BOOLEAN := FALSE;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'user_id'
          AND data_type <> 'uuid'
    ) THEN
        needs_migration := TRUE;
    END IF;

    IF NOT needs_migration THEN
        RETURN;
    END IF;

    -- Drop foreign keys that reference users.user_id so we can alter types.
    -- to_regclass() does not work for constraints, so rely on IF EXISTS clauses.
    ALTER TABLE IF EXISTS refresh_tokens DROP CONSTRAINT IF EXISTS refresh_tokens_user_id_fkey;
    ALTER TABLE IF EXISTS users DROP CONSTRAINT IF EXISTS users_created_by_fkey;

    -- Convert primary key to UUIDs using the deterministic namespace used by Lambdas
    ALTER TABLE users ALTER COLUMN user_id DROP DEFAULT;
    ALTER TABLE users
        ALTER COLUMN user_id TYPE uuid
        USING uuid_generate_v5('6ba7b810-9dad-11d1-80b4-00c04fd430c8'::uuid, 'user:' || user_id::text);
    ALTER TABLE users ALTER COLUMN user_id SET DEFAULT uuid_generate_v4();

    -- Convert created_by references (may be NULL)
    ALTER TABLE users
        ALTER COLUMN created_by TYPE uuid
        USING CASE
            WHEN created_by IS NULL THEN NULL
            ELSE uuid_generate_v5('6ba7b810-9dad-11d1-80b4-00c04fd430c8'::uuid, 'user:' || created_by::text)
        END;

    -- Convert refresh_tokens.user_id if the table exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'refresh_tokens' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE refresh_tokens
            ALTER COLUMN user_id TYPE uuid
            USING uuid_generate_v5('6ba7b810-9dad-11d1-80b4-00c04fd430c8'::uuid, 'user:' || user_id::text);
    END IF;

    -- Recreate foreign keys
    ALTER TABLE users
        ADD CONSTRAINT users_created_by_fkey FOREIGN KEY (created_by)
        REFERENCES users(user_id) ON DELETE SET NULL;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'refresh_tokens'
    ) THEN
        ALTER TABLE refresh_tokens
            ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id)
            REFERENCES users(user_id) ON DELETE CASCADE;
    END IF;
END;
$$;
SQL

echo "Remote databases are ready for use."
