#!/bin/bash
# =============================================================================
# PostgreSQL Multi-Database Initialization Script
# =============================================================================
# This script is executed during PostgreSQL container initialization to create
# additional databases beyond the default POSTGRES_DB.
#
# Database Architecture:
# - housing (POSTGRES_DB): Shared data layer (documents, chunks, knowledge graph)
# - auth_db (AUTH_DB): Authentication service (users, refresh tokens)
#
# Both databases share the same PostgreSQL instance (vizonomy-postgres) but
# maintain logical separation for:
# - Independent scaling and backup strategies
# - Clear ownership boundaries between services
# - Cross-database references use UUIDs without FK constraints
# =============================================================================

set -e

# Create the auth database if it doesn't exist
# The main database (POSTGRES_DB) is created automatically by the postgres image
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create auth database for user management (auth-service, user-service)
    SELECT 'CREATE DATABASE ${AUTH_DB:-auth_db}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${AUTH_DB:-auth_db}')
    \gexec

    -- Grant privileges to the main user
    GRANT ALL PRIVILEGES ON DATABASE ${AUTH_DB:-auth_db} TO $POSTGRES_USER;
EOSQL

# Provision reduced-scope agent database + role without interfering with shared data
AGENT_DB="${AGENT_API_DB:-agent_reduced}"
AGENT_ROLE="${AGENT_API_DB_USER:-agent_api}"
AGENT_PASSWORD="${AGENT_API_DB_PASSWORD:-agent_api_pass}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO
    \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$AGENT_ROLE') THEN
            EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '$AGENT_ROLE', '$AGENT_PASSWORD');
        END IF;
    END
    \$\$;

    SELECT 'CREATE DATABASE ' || quote_ident('$AGENT_DB')
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$AGENT_DB')
    \gexec

    GRANT ALL PRIVILEGES ON DATABASE $AGENT_DB TO $AGENT_ROLE;
EOSQL

# Ensure the reduced-scope database has the necessary privileges and extensions.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AGENT_DB" <<-EOSQL
    GRANT ALL ON SCHEMA public TO $AGENT_ROLE;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $AGENT_ROLE;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $AGENT_ROLE;
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

echo "✅ Database initialization complete:"
echo "   - Primary database: $POSTGRES_DB (shared_data_layer)"
echo "   - Auth database: ${AUTH_DB:-auth_db} (auth-service, user-service)"
echo "   - Agent demo database: $AGENT_DB (Reduced Scope agent-api)"
