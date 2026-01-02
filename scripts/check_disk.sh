#!/usr/bin/env bash
# Check disk and database status on EC2
# Usage: ./scripts/check_disk.sh

set -euo pipefail

# Configuration
SSH_KEY_PATH=${SSH_KEY_PATH:-~/.ssh/house2.pem}
EC2_HOST=${EC2_HOST:-52.207.140.87}
PG_CONTAINER=${PG_CONTAINER:-vizonomy-prod-postgres-1}
PG_USER=${PG_USER:-vizonomy_user}
PG_DB=${PG_DB:-housing}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

log "=== DISK USAGE ==="
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" "df -h /" </dev/null

log ""
log "=== DOCKER VOLUMES ==="
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" "sudo docker system df -v 2>/dev/null | grep -E '(VOLUME|postgres)' | head -5" </dev/null || true

log ""
log "=== DATABASE SIZE ==="
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" \
  "sudo docker exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c \"SELECT pg_size_pretty(pg_database_size('$PG_DB')) as db_size;\"" </dev/null

log ""
log "=== TABLE SIZES ==="
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" \
  "sudo docker exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c \"
SELECT 
  relname as table,
  pg_size_pretty(pg_total_relation_size(relid)) as total,
  pg_size_pretty(pg_relation_size(relid)) as data,
  pg_size_pretty(pg_indexes_size(relid)) as indexes
FROM pg_stat_user_tables 
ORDER BY pg_total_relation_size(relid) DESC 
LIMIT 10;\"" </dev/null

log ""
log "=== ROW COUNTS ==="
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" \
  "sudo docker exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c \"
SELECT 'documents' as table, count(*) as rows FROM documents
UNION ALL
SELECT 'chunks', count(*) FROM chunks
UNION ALL  
SELECT 'ingestion_jobs', count(*) FROM ingestion_jobs;\"" </dev/null

log ""
log "=== TEMP FILES ==="
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" \
  "sudo docker exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c \"
SELECT temp_files, pg_size_pretty(temp_bytes) as temp_size 
FROM pg_stat_database WHERE datname='$PG_DB';\"" </dev/null

log ""
log "=== PG DATA DIR SIZE ==="
ssh -i "$SSH_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=no \
  ec2-user@"$EC2_HOST" \
  "sudo docker exec $PG_CONTAINER du -sh /var/lib/postgresql/data/base/ 2>/dev/null || echo 'Could not check'" </dev/null

log ""
log "Done!"

