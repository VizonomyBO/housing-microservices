#!/usr/bin/env bash
# Run VACUUM on PostgreSQL to reclaim disk space
# Usage: ./scripts/vacuum_db.sh [full|analyze]
#   no args  = VACUUM (fast, marks space reusable)
#   analyze  = VACUUM ANALYZE (fast + updates stats)
#   full     = VACUUM FULL (slow, rewrites tables, reclaims disk)

set -euo pipefail

# Configuration
SSH_KEY_PATH=${SSH_KEY_PATH:-~/.ssh/house2.pem}
EC2_HOST=${EC2_HOST:-52.207.140.87}
PG_CONTAINER=${PG_CONTAINER:-vizonomy-prod-postgres-1}
PG_USER=${PG_USER:-vizonomy_user}
PG_DB=${PG_DB:-housing}

MODE=${1:-analyze}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

log "Starting VACUUM (mode: $MODE)..."

case "$MODE" in
  full)
    SQL_CMD="VACUUM FULL VERBOSE;"
    log "WARNING: VACUUM FULL locks tables and may take a long time!"
    ;;
  analyze)
    SQL_CMD="VACUUM ANALYZE;"
    ;;
  *)
    SQL_CMD="VACUUM;"
    ;;
esac

# Check disk before
log "Checking disk usage before..."
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" "df -h / | tail -1" </dev/null || true

# Run VACUUM
log "Running: $SQL_CMD"
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o ConnectTimeout=300 -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" \
  "sudo docker exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c '$SQL_CMD'" </dev/null

# Check disk after
log "Checking disk usage after..."
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" "df -h / | tail -1" </dev/null || true

log "Done!"

