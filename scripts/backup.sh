#!/usr/bin/env bash
# ============================================================================
# CHATBOT CORE — Database Backup Script
# ============================================================================
# Automated PostgreSQL backup with retention, verification, and off-site sync.
# Designed for cron execution (daily at 2:00 AM).
# ============================================================================
# Usage: ./backup.sh [full|schema|custom] [retention_days]
#   full     — Full pg_dump (default)
#   schema   — Schema-only dump
#   custom   — Custom format (pg_restore compatible)
#
# Cron: 0 2 * * * /opt/chatbot/scripts/backup.sh full 30
# ============================================================================
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
BACKUP_TYPE="${1:-full}"
RETENTION_DAYS="${2:-30}"
BACKUP_DIR="${BACKUP_DIR:-/opt/chatbot/backups}"
LOG_DIR="${LOG_DIR:-/opt/chatbot/logs}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DATE_HUMAN="$(date +%Y-%m-%d\ %H:%M:%S)"

# Database connection (from environment or defaults)
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5433}"
DB_NAME="${DB_NAME:-chatbot}"
DB_USER="${DB_USER:-shared}"
DB_PASSWORD="${DB_PASSWORD:-shared_secret}"

# Off-site sync (optional, set S3_BUCKET to enable)
S3_BUCKET="${S3_BUCKET:-}"
S3_ENDPOINT="${S3_ENDPOINT:-}"

# ── Logging ──────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/backup_${TIMESTAMP}.log"

log() {
    local level="$1"
    shift
    echo "[$DATE_HUMAN] [$level] $*" | tee -a "$LOG_FILE"
}

# ── Pre-flight Checks ────────────────────────────────────────────────────────
log "INFO" "Starting backup: type=$BACKUP_TYPE, retention=$RETENTION_DAYS days"
log "INFO" "Database: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"

if ! command -v pg_dump &>/dev/null; then
    log "ERROR" "pg_dump not found in PATH"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# ── Determine filename and flags ─────────────────────────────────────────────
case "$BACKUP_TYPE" in
    full)
        FILENAME="chatbot_full_${TIMESTAMP}.sql.gz"
        PG_DUMP_FLAGS="--format=plain --no-owner --no-privileges"
        COMPRESS="gzip"
        ;;
    schema)
        FILENAME="chatbot_schema_${TIMESTAMP}.sql"
        PG_DUMP_FLAGS="--schema-only"
        COMPRESS="none"
        ;;
    custom)
        FILENAME="chatbot_custom_${TIMESTAMP}.dump"
        PG_DUMP_FLAGS="--format=custom --compress=6"
        COMPRESS="none"
        ;;
    *)
        log "ERROR" "Unknown backup type: $BACKUP_TYPE (use: full, schema, custom)"
        exit 1
        ;;
esac

BACKUP_PATH="$BACKUP_DIR/$FILENAME"

# ── Execute Backup ───────────────────────────────────────────────────────────
log "INFO" "Running pg_dump: $PG_DUMP_FLAGS"

export PGPASSWORD="$DB_PASSWORD"

if [ "$BACKUP_TYPE" = "full" ]; then
    pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        $PG_DUMP_FLAGS | gzip > "$BACKUP_PATH"
else
    pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        $PG_DUMP_FLAGS > "$BACKUP_PATH"
fi

unset PGPASSWORD

# ── Verify Backup ────────────────────────────────────────────────────────────
if [ ! -f "$BACKUP_PATH" ]; then
    log "ERROR" "Backup file not created: $BACKUP_PATH"
    exit 1
fi

FILE_SIZE="$(du -h "$BACKUP_PATH" | cut -f1)"
log "INFO" "Backup created: $FILENAME ($FILE_SIZE)"

# Verify integrity
if [ "$BACKUP_TYPE" = "full" ]; then
    if ! gzip -t "$BACKUP_PATH" 2>/dev/null; then
        log "ERROR" "Backup integrity check failed (gzip corrupt)"
        rm -f "$BACKUP_PATH"
        exit 1
    fi
    log "INFO" "Integrity check: gzip OK"
elif [ "$BACKUP_TYPE" = "custom" ]; then
    if ! pg_restore --list "$BACKUP_PATH" &>/dev/null; then
        log "ERROR" "Backup integrity check failed (pg_restore cannot read)"
        rm -f "$BACKUP_PATH"
        exit 1
    fi
    log "INFO" "Integrity check: pg_restore OK"
fi

# ── Retention Cleanup ────────────────────────────────────────────────────────
log "INFO" "Cleaning up backups older than $RETENTION_DAYS days"
DELETED_COUNT=0
while IFS= read -r -d '' old_file; do
    log "INFO" "Deleting old backup: $(basename "$old_file")"
    rm -f "$old_file"
    DELETED_COUNT=$((DELETED_COUNT + 1))
done < <(find "$BACKUP_DIR" -name "chatbot_*" -type f -mtime +"$RETENTION_DAYS" -print0)

log "INFO" "Deleted $DELETED_COUNT old backup(s)"

# ── Latest Symlink ───────────────────────────────────────────────────────────
ln -sf "$BACKUP_PATH" "$BACKUP_DIR/latest"
log "INFO" "Updated latest symlink -> $FILENAME"

# ── Off-site Sync (optional) ─────────────────────────────────────────────────
if [ -n "$S3_BUCKET" ]; then
    log "INFO" "Syncing to S3: $S3_BUCKET"
    if command -v aws &>/dev/null; then
        AWS_ARGS=()
        if [ -n "$S3_ENDPOINT" ]; then
            AWS_ARGS+=(--endpoint-url "$S3_ENDPOINT")
        fi
        aws "${AWS_ARGS[@]}" s3 cp "$BACKUP_PATH" "s3://$S3_BUCKET/backups/$FILENAME"
        log "INFO" "S3 sync complete"
    else
        log "WARN" "aws CLI not found, skipping S3 sync"
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
BACKUP_COUNT="$(find "$BACKUP_DIR" -name "chatbot_*" -type f | wc -l)"
TOTAL_SIZE="$(du -sh "$BACKUP_DIR" | cut -f1)"

log "INFO" "=== Backup Summary ==="
log "INFO" "Type: $BACKUP_TYPE"
log "INFO" "File: $FILENAME"
log "INFO" "Size: $FILE_SIZE"
log "INFO" "Total backups: $BACKUP_COUNT"
log "INFO" "Total disk usage: $TOTAL_SIZE"
log "INFO" "Retention: $RETENTION_DAYS days"
log "INFO" "Off-site: ${S3_BUCKET:-disabled}"
log "INFO" "Backup completed successfully"

exit 0
