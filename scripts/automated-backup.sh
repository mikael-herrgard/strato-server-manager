#!/bin/bash
# Automated Backup Script
# Called by cron for scheduled backups

set -e

# Configuration
BASE_DIR="/opt/server-manager"
VENV_PYTHON="${BASE_DIR}/venv/bin/python3"
CLI="${BASE_DIR}/cli.py"

# Parse arguments
SERVICE="$1"
shift || true

VERIFY_FLAG=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --verify)
            VERIFY_FLAG="--verify"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Validate service
if [[ -z "$SERVICE" ]]; then
    echo "Error: Service name required"
    echo "Usage: $0 <service> [--verify]"
    exit 1
fi

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting automated backup: $SERVICE"

# Run the backup via CLI entry point
BACKUP_CMD=("$VENV_PYTHON" "$CLI" backup "$SERVICE")
[ -n "$VERIFY_FLAG" ] && BACKUP_CMD+=("$VERIFY_FLAG")

if "${BACKUP_CMD[@]}"; then
    log "Backup completed successfully: $SERVICE"
    exit 0
else
    log "Backup failed: $SERVICE"
    exit 1
fi
