#!/bin/bash
# Automated Backup Cleanup Script
# Called by cron to remove old backups

set -e

# Configuration
BASE_DIR="/opt/server-manager"
VENV_PYTHON="${BASE_DIR}/venv/bin/python3"
CLI="${BASE_DIR}/cli.py"

# Parse arguments
RETENTION_DAYS="${1:-30}"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting automated backup cleanup (retention: $RETENTION_DAYS days)"

# Run the cleanup via CLI entry point
if "$VENV_PYTHON" "$CLI" cleanup --retention-days "$RETENTION_DAYS"; then
    log "Cleanup completed successfully"
    exit 0
else
    log "Cleanup completed with errors"
    exit 1
fi
