#!/bin/bash
# =============================================================================
# PostgreSQL Multi-Database Initialization Script
# =============================================================================
# This script is executed during PostgreSQL container initialization to create
# the logical databases used by the stack.
#
# Database Architecture:
# - housing (POSTGRES_DB): Agent API + ingestion (shared data layer)
# - auth_db (AUTH_DB): Authentication + user services
#
# Both databases share the same PostgreSQL instance (housing-postgres) but keep
# logical separation for ownership and backup boundaries. Cross-database
# references use UUIDs without FK constraints.
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

# Ensure pgvector is available in the primary database
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

echo "✅ Database initialization complete:"
echo "   - Primary database: $POSTGRES_DB (shared_data_layer)"
echo "   - Auth database: ${AUTH_DB:-auth_db} (auth-service, user-service)"
