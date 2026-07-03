#!/bin/bash
# Borg Repository Integrity Check
# Called by cron monthly (1st, 06:00) — verifies all Borg repositories
# with 'borg check'. Failure emails are sent by cli.py.

set -e

BASE_DIR="/opt/server-manager"
VENV_PYTHON="${BASE_DIR}/venv/bin/python3"
CLI="${BASE_DIR}/cli.py"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting Borg repository integrity check"

if "$VENV_PYTHON" "$CLI" check all; then
    log "All repository checks passed"
    exit 0
else
    log "Repository check FAILED — see notification email / server-manager.log"
    exit 1
fi
