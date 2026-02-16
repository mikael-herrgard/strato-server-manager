#!/usr/bin/env python3
"""
Server Manager CLI
Entry point for automated backup and cleanup operations called by cron.
"""

import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

# Ensure the server-manager root is on the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.backup import BackupManager
from lib.notifications import NotificationManager


def cmd_backup(args):
    """Run a backup for the specified service."""
    service = args.service
    verify = args.verify

    backup_mgr = BackupManager()
    notif_mgr = NotificationManager()

    start_time = datetime.now()

    try:
        if service == "nginx":
            success = backup_mgr.backup_nginx(verify=verify)
        elif service == "mailcow":
            success = backup_mgr.backup_mailcow(backup_type="all", verify=verify)
        elif service == "mailcow-directory":
            success = backup_mgr.backup_mailcow_directory(verify=verify)
        elif service == "server-manager":
            success = backup_mgr.backup_server_manager(verify=verify)
        else:
            print(f"Error: Unknown service: {service}")
            sys.exit(1)

        duration = (datetime.now() - start_time).total_seconds()

        if success:
            print(f"Backup completed successfully in {duration:.2f} seconds")
            notif_mgr.send_backup_notification(
                service, True,
                {'duration': f"{duration:.2f} seconds", 'verified': verify}
            )
        else:
            print("Backup failed")
            notif_mgr.send_backup_notification(
                service, False,
                {'error': 'Backup operation returned false', 'duration': f"{duration:.2f} seconds"}
            )
            sys.exit(1)

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        print(f"Backup error: {e}")
        notif_mgr.send_backup_notification(
            service, False,
            {'error': str(e), 'duration': f"{duration:.2f} seconds"}
        )
        sys.exit(1)


def cmd_cleanup(args):
    """Run backup cleanup with the specified retention period."""
    retention_days = args.retention_days
    backup_dir = Path("/opt/server-manager/backups")

    if not backup_dir.exists():
        print("Backup directory does not exist")
        return

    notif_mgr = NotificationManager()

    from datetime import timedelta
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    print(f"Removing backups older than {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")

    removed_count = 0
    removed_size = 0
    errors = []

    for service_dir in backup_dir.iterdir():
        if not service_dir.is_dir():
            continue

        print(f"Checking service: {service_dir.name}")

        for backup_file in service_dir.iterdir():
            try:
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

    if removed_count > 0 or errors:
        notif_mgr.send_maintenance_notification(
            "Backup Cleanup",
            len(errors) == 0,
            {
                'files_removed': removed_count,
                'space_freed': size_str,
                'retention_days': retention_days,
                'errors': len(errors)
            }
        )

    sys.exit(0 if len(errors) == 0 else 1)


def main():
    parser = argparse.ArgumentParser(
        description="Server Manager CLI for automated backup and cleanup operations"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # backup subcommand
    backup_parser = subparsers.add_parser("backup", help="Run a backup")
    backup_parser.add_argument(
        "service",
        choices=["nginx", "mailcow", "mailcow-directory", "server-manager"],
        help="Service to back up"
    )
    backup_parser.add_argument(
        "--verify", action="store_true", default=False,
        help="Verify backup after creation"
    )
    backup_parser.set_defaults(func=cmd_backup)

    # cleanup subcommand
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old backups")
    cleanup_parser.add_argument(
        "--retention-days", type=int, default=30,
        help="Days to retain backups (default: 30)"
    )
    cleanup_parser.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
