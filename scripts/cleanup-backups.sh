#!/bin/bash
# Automated Backup Cleanup Script
# Called by cron to remove old backups

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="/opt/server-manager"
VENV_PYTHON="${BASE_DIR}/venv/bin/python3"
LOG_DIR="${BASE_DIR}/logs"
BACKUP_DIR="${BASE_DIR}/backups"

# Parse arguments
RETENTION_DAYS="${1:-30}"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting automated backup cleanup"
log "Retention period: $RETENTION_DAYS days"

# Validate retention period
if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    log "Error: Invalid retention period: $RETENTION_DAYS"
    exit 1
fi

if [[ "$RETENTION_DAYS" -lt 1 ]]; then
    log "Error: Retention period must be at least 1 day"
    exit 1
fi

# Create temporary Python script to run cleanup
TEMP_SCRIPT=$(mktemp)
cat > "$TEMP_SCRIPT" << 'EOFPYTHON'
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, "/opt/server-manager")

from lib.notifications import NotificationManager

retention_days = int(sys.argv[1])
backup_dir = Path("/opt/server-manager/backups")

if not backup_dir.exists():
    print("Backup directory does not exist")
    sys.exit(0)

notif_mgr = NotificationManager()

cutoff_date = datetime.now() - timedelta(days=retention_days)
print(f"Removing backups older than {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")

removed_count = 0
removed_size = 0
errors = []

# Walk through backup directory
for service_dir in backup_dir.iterdir():
    if not service_dir.is_dir():
        continue

    print(f"Checking service: {service_dir.name}")

    for backup_file in service_dir.iterdir():
        try:
            # Get file modification time
            mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)

            if mtime < cutoff_date:
                file_size = backup_file.stat().st_size
                print(f"  Removing: {backup_file.name} (age: {(datetime.now() - mtime).days} days)")

                backup_file.unlink()
                removed_count += 1
                removed_size += file_size

        except Exception as e:
            error_msg = f"Error removing {backup_file}: {e}"
            print(f"  {error_msg}")
            errors.append(error_msg)

# Convert size to human readable
if removed_size > 1024**3:
    size_str = f"{removed_size / 1024**3:.2f} GB"
elif removed_size > 1024**2:
    size_str = f"{removed_size / 1024**2:.2f} MB"
elif removed_size > 1024:
    size_str = f"{removed_size / 1024:.2f} KB"
else:
    size_str = f"{removed_size} bytes"

print(f"\nCleanup completed:")
print(f"  Files removed: {removed_count}")
print(f"  Space freed: {size_str}")

if errors:
    print(f"  Errors: {len(errors)}")

# Send notification
if removed_count > 0 or errors:
    details = {
        'files_removed': removed_count,
        'space_freed': size_str,
        'retention_days': retention_days,
        'errors': len(errors)
    }

    notif_mgr.send_maintenance_notification(
        "Backup Cleanup",
        len(errors) == 0,
        details
    )

sys.exit(0 if len(errors) == 0 else 1)
EOFPYTHON

# Run the cleanup
if "$VENV_PYTHON" "$TEMP_SCRIPT" "$RETENTION_DAYS"; then
    log "Cleanup completed successfully"
    rm -f "$TEMP_SCRIPT"
    exit 0
else
    log "Cleanup completed with errors"
    rm -f "$TEMP_SCRIPT"
    exit 1
fi
