#!/usr/bin/env bash
# ============================================================================
# CHATBOT CORE — Database Restore Script
# ============================================================================
# Restores a chatbot database backup with pre-flight checks and safety.
# ============================================================================
# Usage: ./restore.sh <backup_file> [target_db]
#   backup_file — Path to backup file (or 'latest' for most recent)
#   target_db   — Target database name (default: chatbot)
#
# Examples:
#   ./restore.sh latest
#   ./restore.sh /opt/chatbot/backups/chatbot_full_20260521_020000.sql.gz
#   ./restore.sh chatbot_custom_20260520.dump chatbot_staging
# ============================================================================
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
BACKUP_FILE="${1:-}"
TARGET_DB="${2:-chatbot}"
BACKUP_DIR="${BACKUP_DIR:-/opt/chatbot/backups}"
LOG_DIR="${LOG_DIR:-/opt/chatbot/logs}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DATE_HUMAN="$(date +%Y-%m-%d\ %H:%M:%S)"

# Database connection
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5433}"
DB_USER="${DB_USER:-shared}"
DB_PASSWORD="${DB_PASSWORD:-shared_secret}"

# Safety: require explicit confirmation for production
FORCE="${FORCE:-}"

# ── Logging ──────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/restore_${TIMESTAMP}.log"

log() {
    local level="$1"
    shift
    echo "[$DATE_HUMAN] [$level] $*" | tee -a "$LOG_FILE"
}

# ── Pre-flight Checks ────────────────────────────────────────────────────────
if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file> [target_db]"
    echo ""
    echo "Available backups:"
    ls -lht "$BACKUP_DIR"/chatbot_* 2>/dev/null | head -10 || echo "  (none found)"
    exit 1
fi

# Resolve 'latest' symlink
if [ "$BACKUP_FILE" = "latest" ]; then
    BACKUP_FILE="$BACKUP_DIR/latest"
    if [ ! -e "$BACKUP_FILE" ]; then
        log "ERROR" "No latest backup found. Run backup.sh first."
        exit 1
    fi
    BACKUP_FILE="$(readlink -f "$BACKUP_FILE")"
fi

# Resolve relative paths
if [[ "$BACKUP_FILE" != /* ]]; then
    BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
fi

if [ ! -f "$BACKUP_FILE" ]; then
    log "ERROR" "Backup file not found: $BACKUP_FILE"
    exit 1
fi

log "INFO" "Restore target: $TARGET_DB"
log "INFO" "Backup file: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# ── Safety Confirmation ──────────────────────────────────────────────────────
if [ "$TARGET_DB" = "chatbot" ] && [ -z "$FORCE" ]; then
    log "WARN" "WARNING: You are about to restore to the PRODUCTION database!"
    log "WARN" "This will OVERWRITE all existing data."
    log "WARN" "Set FORCE=1 to skip this confirmation."
    echo ""
    read -rp "Type 'RESTORE' to confirm: " confirmation
    if [ "$confirmation" != "RESTORE" ]; then
        log "INFO" "Restore cancelled by user"
        exit 0
    fi
fi

# ── Detect Backup Type ───────────────────────────────────────────────────────
detect_backup_type() {
    local file="$1"
    local ext="${file##*.}"

    case "$ext" in
        gz)
            echo "full_gz"
            ;;
        sql)
            echo "full_plain"
            ;;
        dump)
            echo "custom"
            ;;
        *)
            # Try to detect by content
            if file "$file" | grep -q "gzip"; then
                echo "full_gz"
            elif file "$file" | grep -q "PostgreSQL custom"; then
                echo "custom"
            else
                echo "full_plain"
            fi
            ;;
    esac
}

BACKUP_TYPE="$(detect_backup_type "$BACKUP_FILE")"
log "INFO" "Detected backup type: $BACKUP_TYPE"

export PGPASSWORD="$DB_PASSWORD"

# ── Create Target Database if Needed ─────────────────────────────────────────
DB_EXISTS="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tc \
    "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB'" | tr -d ' ')"

if [ "$DB_EXISTS" != "1" ]; then
    log "INFO" "Creating database: $TARGET_DB"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE $TARGET_DB;"
fi

# ── Terminate Existing Connections ───────────────────────────────────────────
log "INFO" "Terminating existing connections to $TARGET_DB"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TARGET_DB' AND pid <> pg_backend_pid();" 2>/dev/null || true

# ── Execute Restore ──────────────────────────────────────────────────────────
log "INFO" "Starting restore..."

case "$BACKUP_TYPE" in
    full_gz)
        gunzip -c "$BACKUP_FILE" | psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB"
        ;;
    full_plain)
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" -f "$BACKUP_FILE"
        ;;
    custom)
        pg_restore \
            -h "$DB_HOST" \
            -p "$DB_PORT" \
            -U "$DB_USER" \
            -d "$TARGET_DB" \
            --no-owner \
            --no-privileges \
            --clean \
            --if-exists \
            "$BACKUP_FILE"
        ;;
esac

unset PGPASSWORD

# ── Post-Restore Verification ────────────────────────────────────────────────
log "INFO" "Running post-restore verification..."

TABLE_COUNT="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" -tc \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'" | tr -d ' ')"

ROW_COUNT="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" -tc \
    "SELECT COALESCE(SUM(n_live_tup), 0) FROM pg_stat_user_tables" | tr -d ' ')"

log "INFO" "Tables restored: $TABLE_COUNT"
log "INFO" "Approximate rows: $ROW_COUNT"

# Verify critical tables exist
CRITICAL_TABLES="tenants users conversations messages knowledge_base products"
for table in $CRITICAL_TABLES; do
    EXISTS="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" -tc \
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '$table'" | tr -d ' ')"
    if [ "$EXISTS" = "1" ]; then
        log "INFO" "  Table '$table': OK"
    else
        log "WARN" "  Table '$table': MISSING"
    fi
done

# ── Run ANALYZE for Query Planner ────────────────────────────────────────────
log "INFO" "Running ANALYZE for query planner optimization..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" -c "ANALYZE;" 2>/dev/null || true

# ── Summary ──────────────────────────────────────────────────────────────────
log "INFO" "=== Restore Summary ==="
log "INFO" "Backup: $(basename "$BACKUP_FILE")"
log "INFO" "Target: $TARGET_DB"
log "INFO" "Type: $BACKUP_TYPE"
log "INFO" "Tables: $TABLE_COUNT"
log "INFO" "Rows: ~$ROW_COUNT"
log "INFO" "Restore completed successfully"

exit 0
