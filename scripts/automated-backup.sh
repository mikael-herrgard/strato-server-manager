#!/bin/bash
# Automated Backup Script
# Called by cron for scheduled backups

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="/opt/server-manager"
VENV_PYTHON="${BASE_DIR}/venv/bin/python3"
LOG_DIR="${BASE_DIR}/logs"
NOTIFICATION_SCRIPT="${SCRIPT_DIR}/send-notification.sh"

# Parse arguments
SERVICE="$1"
VERIFY=false
REMOTE=false

shift
while [[ $# -gt 0 ]]; do
    case $1 in
        --verify)
            VERIFY=true
            shift
            ;;
        --remote)
            REMOTE=true
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
    echo "Usage: $0 <service> [--verify] [--remote]"
    exit 1
fi

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting automated backup: $SERVICE"
log "Options: verify=$VERIFY, remote=$REMOTE"

# Create temporary Python script to run backup
TEMP_SCRIPT=$(mktemp)
cat > "$TEMP_SCRIPT" << 'EOFPYTHON'
import sys
import os
sys.path.insert(0, "/opt/server-manager")

from lib.backup import BackupManager
from lib.notifications import NotificationManager
from datetime import datetime

service = sys.argv[1]
verify = sys.argv[2] == "true"
remote = sys.argv[3] == "true"

backup_mgr = BackupManager()
notif_mgr = NotificationManager()

start_time = datetime.now()

try:
    # Perform backup
    if service == "nginx":
        success = backup_mgr.backup_nginx(verify=verify)
    elif service == "mailcow":
        success = backup_mgr.backup_mailcow(backup_type="all", verify=verify)
    elif service == "mailcow-directory":
        success = backup_mgr.backup_mailcow_directory(verify=verify)
    else:
        print(f"Error: Unknown service: {service}")
        sys.exit(1)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    if success:
        print(f"Backup completed successfully in {duration:.2f} seconds")

        # Send notification
        notif_mgr.send_backup_notification(
            service,
            True,
            {
                'duration': f"{duration:.2f} seconds",
                'verified': verify,
                'remote': remote
            }
        )

        sys.exit(0)
    else:
        print(f"Backup failed")

        # Send failure notification
        notif_mgr.send_backup_notification(
            service,
            False,
            {
                'error': 'Backup operation returned false',
                'duration': f"{duration:.2f} seconds"
            }
        )

        sys.exit(1)

except Exception as e:
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print(f"Backup error: {e}")

    # Send failure notification
    notif_mgr.send_backup_notification(
        service,
        False,
        {
            'error': str(e),
            'duration': f"{duration:.2f} seconds"
        }
    )

    sys.exit(1)
EOFPYTHON

# Run the backup
if "$VENV_PYTHON" "$TEMP_SCRIPT" "$SERVICE" "$VERIFY" "$REMOTE"; then
    log "Backup completed successfully: $SERVICE"
    rm -f "$TEMP_SCRIPT"
    exit 0
else
    log "Backup failed: $SERVICE"
    rm -f "$TEMP_SCRIPT"
    exit 1
fi
