#!/bin/bash
# TGMA Database Backup Script
# Run daily via cron:
#   0 2 * * * /opt/tgma-platform/scripts/backup.sh >> /var/log/tgma/backup.log 2>&1

set -euo pipefail

BACKUP_DIR="/opt/tgma-backups"
DB_NAME="${POSTGRES_DB:-tgma_db}"
DB_USER="${POSTGRES_USER:-tgma_user}"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/tgma_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting backup..."

# PostgreSQL custom format backup (supports parallel restore)
pg_dump \
    --dbname="${DB_NAME}" \
    --username="${DB_USER}" \
    --format=custom \
    --compress=6 \
    --file="${BACKUP_FILE}"

FILESIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Backup created: ${BACKUP_FILE} (${FILESIZE})"

# Clean up old backups
DELETED=$(find "${BACKUP_DIR}" -name "tgma_*.dump" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "[$(date)] Deleted ${DELETED} backups older than ${RETENTION_DAYS} days"
fi

echo "[$(date)] Backup complete"
